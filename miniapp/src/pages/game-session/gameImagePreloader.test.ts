import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const taroMock = vi.hoisted(() => ({ getImageInfo: vi.fn() }))
vi.mock('@tarojs/taro', () => ({ default: taroMock }))

import { PublicRequestError } from '../../api/client'
import {
  parseSignedAssetManifest,
  SignedAssetManifestError,
  type SignedAssetManifest,
} from '../../assets/signedAssetManifest'
import { signedAssetFixture } from '../../assets/signedAssetFixtures.test-helper'
import { gameImageRemoteUrl, type GameImageKey } from './gameImageAssets'
import { GameImagePreloadCancelledError, preloadGameImages, taroGetImageInfo } from './gameImagePreloader'

const KEYS = ['pattern_sun', 'pattern_coconut', 'pattern_boat', 'pattern_lighthouse'] as const
let manifest: SignedAssetManifest

beforeEach(() => {
  vi.stubEnv('TARO_APP_ASSET_BASE_URL', 'https://cdn.example.com/motioncare/static-assets')
  manifest = parseSignedAssetManifest(signedAssetFixture())
  vi.clearAllMocks()
})
afterEach(() => vi.unstubAllEnvs())

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, reject, resolve }
}

type Pending = { key: GameImageKey; reject: (reason?: unknown) => void; resolve: (value: { path: string }) => void }
function controlledDownloads() {
  let active = 0
  let peak = 0
  const pending: Pending[] = []
  const startedKeys: GameImageKey[] = []
  const sourceToKey = new Map(KEYS.map((key) => [gameImageRemoteUrl(key, manifest), key]))
  const getImageInfo = ({ src }: { src: string }) => {
    const key = sourceToKey.get(src)
    if (!key) throw new Error(`unexpected source: ${src}`)
    startedKeys.push(key); active += 1; peak = Math.max(peak, active)
    return new Promise<{ path: string }>((resolve, reject) => pending.push({
      key,
      resolve: (value) => { active -= 1; resolve(value) },
      reject: (reason) => { active -= 1; reject(reason) },
    }))
  }
  return { get active() { return active }, get peak() { return peak }, getImageInfo, pending, startedKeys }
}
async function flush(times = 8) { for (let index = 0; index < times; index += 1) await Promise.resolve() }
function resolveAt(controlled: ReturnType<typeof controlledDownloads>, index = 0) {
  const request = controlled.pending.splice(index, 1)[0]
  if (!request) throw new Error('expected pending request')
  request.resolve({ path: `/tmp/${request.key}.webp` })
}

describe('preloadGameImages', () => {
  it('下载失败只刷新一次并返回临时文件', async () => {
    const loadSignedManifest = vi.fn().mockResolvedValue(manifest)
    const getImageInfo = vi.fn().mockRejectedValueOnce(new Error('下载失败')).mockResolvedValueOnce({ path: '/tmp/sun.webp' })
    const paths = await preloadGameImages(['pattern_sun'], {
      getImageInfo, loadSignedManifest, isCurrent: () => true, onProgress: vi.fn(),
    })
    expect(paths.pattern_sun).toBe('/tmp/sun.webp')
    expect(loadSignedManifest.mock.calls).toEqual([[], [{ forceRefresh: true }]])
    expect(getImageInfo).toHaveBeenCalledTimes(2)
  })

  it('没有图片时不获取清单', async () => {
    const loadSignedManifest = vi.fn()
    const onProgress = vi.fn()
    await expect(preloadGameImages([], {
      getImageInfo: vi.fn(), loadSignedManifest, isCurrent: () => true, onProgress,
    })).resolves.toEqual({})
    expect(loadSignedManifest).not.toHaveBeenCalled()
    expect(onProgress).toHaveBeenLastCalledWith({ completed: 0, total: 0, percent: 100 })
  })

  it('清单未返回就退出时不下载', async () => {
    const pendingManifest = deferred<SignedAssetManifest>()
    const getImageInfo = vi.fn()
    let current = true
    const loading = preloadGameImages(['pattern_sun'], {
      getImageInfo, loadSignedManifest: () => pendingManifest.promise, isCurrent: () => current, onProgress: vi.fn(),
    })
    current = false
    pendingManifest.resolve(manifest)
    await expect(loading).rejects.toBeInstanceOf(GameImagePreloadCancelledError)
    expect(getImageInfo).not.toHaveBeenCalled()
  })

  it('初始已取消时不请求清单或下载', async () => {
    const loadSignedManifest = vi.fn()
    const getImageInfo = vi.fn()
    await expect(preloadGameImages(['pattern_sun'], {
      getImageInfo, loadSignedManifest, isCurrent: () => false, onProgress: vi.fn(),
    })).rejects.toBeInstanceOf(GameImagePreloadCancelledError)
    expect(loadSignedManifest).not.toHaveBeenCalled()
    expect(getImageInfo).not.toHaveBeenCalled()
  })

  it('下载途中退出时不更新进度', async () => {
    const image = deferred<{ path: string }>()
    const onProgress = vi.fn()
    let current = true
    const loading = preloadGameImages(['pattern_sun'], {
      getImageInfo: () => image.promise, loadSignedManifest: vi.fn().mockResolvedValue(manifest),
      isCurrent: () => current, onProgress,
    })
    await flush(); current = false; image.resolve({ path: '/tmp/sun.webp' })
    await expect(loading).rejects.toBeInstanceOf(GameImagePreloadCancelledError)
    expect(onProgress.mock.calls).toEqual([[{ completed: 0, total: 1, percent: 0 }]])
  })

  it('取消后的异步下载拒绝归一为取消且不刷新', async () => {
    const image = deferred<{ path: string }>()
    const loadSignedManifest = vi.fn().mockResolvedValue(manifest)
    let current = true
    const loading = preloadGameImages(['pattern_sun'], {
      getImageInfo: () => image.promise, loadSignedManifest,
      isCurrent: () => current, onProgress: vi.fn(),
    })
    await flush(); current = false; image.reject(new Error('下载失败'))
    await expect(loading).rejects.toBeInstanceOf(GameImagePreloadCancelledError)
    expect(loadSignedManifest).toHaveBeenCalledTimes(1)
  })

  it('记录下载失败后会话失效时等待旧 worker 并直接取消', async () => {
    const first = deferred<{ path: string }>()
    const second = deferred<{ path: string }>()
    const loadSignedManifest = vi.fn().mockResolvedValue(manifest)
    const getImageInfo = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    let current = true
    const loading = preloadGameImages(['pattern_sun', 'pattern_coconut'], {
      getImageInfo, loadSignedManifest, isCurrent: () => current, onProgress: vi.fn(),
    })
    await flush(); first.reject(new Error('下载失败')); await Promise.resolve(); current = false
    second.resolve({ path: '/tmp/late.webp' })
    await expect(loading).rejects.toBeInstanceOf(GameImagePreloadCancelledError)
    expect(loadSignedManifest).toHaveBeenCalledTimes(1)
  })

  it('undefined rejection 会终止本轮且迟到成功不写进度', async () => {
    const first = deferred<{ path: string }>()
    const second = deferred<{ path: string }>()
    const onProgress = vi.fn()
    const getImageInfo = vi.fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
      .mockRejectedValue(new Error('第二轮失败'))
    const loading = preloadGameImages(['pattern_sun', 'pattern_coconut'], {
      getImageInfo, loadSignedManifest: vi.fn().mockResolvedValue(manifest),
      isCurrent: () => true, onProgress,
    })
    await flush(); first.reject(undefined); await Promise.resolve()
    second.resolve({ path: '/tmp/late.webp' })
    await expect(loading).rejects.toThrow('训练素材暂时不可用，请稍后重试')
    expect(onProgress.mock.calls).toEqual([[{ completed: 0, total: 2, percent: 0 }]])
  })

  it('连续两次下载失败后结束且错误消息脱敏', async () => {
    const loadSignedManifest = vi.fn().mockResolvedValue(manifest)
    const getImageInfo = vi.fn().mockRejectedValue(new Error('https://secret.example/?token=abc'))
    await expect(preloadGameImages(['pattern_sun'], {
      getImageInfo, loadSignedManifest, isCurrent: () => true, onProgress: vi.fn(),
    })).rejects.toThrow('训练素材暂时不可用，请稍后重试')
    expect(loadSignedManifest).toHaveBeenCalledTimes(2)
    expect(getImageInfo).toHaveBeenCalledTimes(2)
  })

  it.each([404, 429])('%s 清单错误不强制刷新', async (statusCode) => {
    const loadSignedManifest = vi.fn().mockRejectedValue(new PublicRequestError('失败', statusCode))
    await expect(preloadGameImages(['pattern_sun'], {
      getImageInfo: vi.fn(), loadSignedManifest, isCurrent: () => true, onProgress: vi.fn(),
    })).rejects.toThrow('训练素材暂时不可用，请稍后重试')
    expect(loadSignedManifest).toHaveBeenCalledTimes(1)
  })

  it('多个下载同时失败仍只强制刷新一次', async () => {
    const loadSignedManifest = vi.fn().mockResolvedValue(manifest)
    await expect(preloadGameImages(KEYS.slice(0, 3), {
      getImageInfo: vi.fn().mockRejectedValue(new Error('下载失败')), loadSignedManifest,
      isCurrent: () => true, onProgress: vi.fn(),
    })).rejects.toThrow('训练素材暂时不可用，请稍后重试')
    expect(loadSignedManifest.mock.calls).toEqual([[], [{ forceRefresh: true }]])
  })

  it('清单刷新耗尽共享预算后下载失败不再请求第三份清单', async () => {
    const loadSignedManifest = vi.fn()
      .mockRejectedValueOnce(new SignedAssetManifestError(true))
      .mockResolvedValueOnce(manifest)
    const getImageInfo = vi.fn().mockRejectedValue(new Error('下载失败'))
    await expect(preloadGameImages(['pattern_sun'], {
      getImageInfo, loadSignedManifest, isCurrent: () => true, onProgress: vi.fn(),
    })).rejects.toThrow('训练素材暂时不可用，请稍后重试')
    expect(loadSignedManifest.mock.calls).toEqual([[], [{ forceRefresh: true }]])
    expect(getImageInfo).toHaveBeenCalledTimes(1)
  })

  it('旧一轮全部结束后才重试并保持峰值并发三', async () => {
    const controlled = controlledDownloads()
    const loading = preloadGameImages(KEYS, {
      getImageInfo: controlled.getImageInfo, loadSignedManifest: vi.fn().mockResolvedValue(manifest),
      isCurrent: () => true, onProgress: vi.fn(),
    })
    await flush()
    expect(controlled.active).toBe(3)
    controlled.pending.splice(0, 1)[0].reject(new Error('下载失败'))
    await flush()
    expect(controlled.startedKeys).toHaveLength(3)
    resolveAt(controlled, 0); await flush()
    expect(controlled.startedKeys).toHaveLength(3)
    resolveAt(controlled, 0); await flush()
    expect(controlled.startedKeys).toHaveLength(6)
    while (controlled.pending.length) resolveAt(controlled)
    await flush()
    while (controlled.pending.length) resolveAt(controlled)
    await expect(loading).resolves.toHaveProperty('pattern_sun')
    expect(controlled.peak).toBe(3)
  })

  it('已成功图片不重复下载且进度只增不减', async () => {
    const progress: number[] = []
    const attempts = new Map<GameImageKey, number>()
    await preloadGameImages(KEYS.slice(0, 3), {
      getImageInfo: async ({ src }) => {
        const key = KEYS.find((candidate) => gameImageRemoteUrl(candidate, manifest) === src)!
        attempts.set(key, (attempts.get(key) ?? 0) + 1)
        if (key === 'pattern_boat' && attempts.get(key) === 1) throw new Error('下载失败')
        return { path: `/tmp/${key}.webp` }
      },
      loadSignedManifest: vi.fn().mockResolvedValue(manifest), isCurrent: () => true,
      onProgress: ({ completed }) => progress.push(completed),
    })
    expect([...attempts.entries()]).toEqual([
      ['pattern_sun', 1], ['pattern_coconut', 1], ['pattern_boat', 2],
    ])
    expect(progress).toEqual([0, 1, 2, 3])
  })

  it('去重并维持三并发', async () => {
    const controlled = controlledDownloads()
    const loading = preloadGameImages([...KEYS, 'pattern_sun'], {
      getImageInfo: controlled.getImageInfo, loadSignedManifest: vi.fn().mockResolvedValue(manifest),
      isCurrent: () => true, onProgress: vi.fn(),
    })
    await flush(); expect(controlled.active).toBe(3); resolveAt(controlled); await flush()
    while (controlled.pending.length) resolveAt(controlled)
    await expect(loading).resolves.toHaveProperty('pattern_lighthouse')
    expect(controlled.peak).toBe(3)
    expect(controlled.startedKeys).toHaveLength(4)
  })

  it('非正并发归一为单 worker', async () => {
    const controlled = controlledDownloads()
    const loading = preloadGameImages(['pattern_sun', 'pattern_coconut'], {
      getImageInfo: controlled.getImageInfo, loadSignedManifest: vi.fn().mockResolvedValue(manifest),
      isCurrent: () => true, onProgress: vi.fn(), concurrency: 0,
    })
    await flush(); expect(controlled.active).toBe(1); resolveAt(controlled); await flush()
    expect(controlled.active).toBe(1); resolveAt(controlled)
    await expect(loading).resolves.toHaveProperty('pattern_coconut')
    expect(controlled.peak).toBe(1)
  })
})

describe('taroGetImageInfo', () => {
  it('使用 Taro 临时图片路径', async () => {
    taroMock.getImageInfo.mockResolvedValue({ path: 'wxfile://prepared/image.webp' })
    await expect(taroGetImageInfo({ src: 'https://cdn.example.com/image.webp' })).resolves.toEqual({ path: 'wxfile://prepared/image.webp' })
  })
})
