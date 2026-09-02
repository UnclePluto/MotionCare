import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const taroMock = vi.hoisted(() => ({
  getImageInfo: vi.fn(),
}))

vi.mock('@tarojs/taro', () => ({ default: taroMock }))

import {
  GameImagePreloadCancelledError,
  preloadGameImages,
  taroGetImageInfo,
  type GameImageLoadProgress,
} from './gameImagePreloader'
import { gameImageRemoteUrl, type GameImageKey } from './gameImageAssets'

const KEYS = ['pattern_sun', 'pattern_coconut', 'pattern_boat', 'pattern_lighthouse'] as const

beforeEach(() => {
  vi.stubEnv('TARO_APP_ASSET_BASE_URL', 'https://cdn.example.com/assets/')
  vi.clearAllMocks()
})

afterEach(() => {
  vi.unstubAllEnvs()
})

type DeferredImageInfo = {
  key: GameImageKey
  reject: (reason?: unknown) => void
  resolve: (value: { path: string }) => void
}

function createControlledImageInfo() {
  let active = 0
  let peak = 0
  const pending: DeferredImageInfo[] = []
  const startedKeys: GameImageKey[] = []
  const sourceToKey = new Map(KEYS.map((key) => [gameImageRemoteUrl(key), key]))

  const getImageInfo = ({ src }: { src: string }) => {
    const key = sourceToKey.get(src)
    if (!key) throw new Error(`unexpected source: ${src}`)

    startedKeys.push(key)
    active += 1
    peak = Math.max(peak, active)
    return new Promise<{ path: string }>((resolve, reject) => {
      pending.push({
        key,
        resolve: (value) => {
          active -= 1
          resolve(value)
        },
        reject: (reason) => {
          active -= 1
          reject(reason)
        },
      })
    })
  }

  return {
    get active() {
      return active
    },
    get peak() {
      return peak
    },
    getImageInfo,
    pending,
    startedKeys,
  }
}

async function flushWorkers() {
  await Promise.resolve()
  await Promise.resolve()
}

function resolveNext(controlled: ReturnType<typeof createControlledImageInfo>) {
  const request = controlled.pending.shift()
  if (!request) throw new Error('expected a pending image request')
  request.resolve({ path: `wxfile://prepared/${request.key}.webp` })
}

describe('preloadGameImages', () => {
  it('does not start a fourth request until one of the first three settles', async () => {
    const controlled = createControlledImageInfo()
    const loading = preloadGameImages(KEYS, {
      getImageInfo: controlled.getImageInfo,
      isCurrent: () => true,
      onProgress: vi.fn(),
    })

    await flushWorkers()
    expect(controlled.active).toBe(3)
    expect(controlled.peak).toBe(3)
    expect(controlled.pending).toHaveLength(3)

    resolveNext(controlled)
    await flushWorkers()
    expect(controlled.peak).toBe(3)
    expect(controlled.active).toBe(3)

    resolveNext(controlled)
    resolveNext(controlled)
    resolveNext(controlled)

    await expect(loading).resolves.toEqual({
      pattern_sun: 'wxfile://prepared/pattern_sun.webp',
      pattern_coconut: 'wxfile://prepared/pattern_coconut.webp',
      pattern_boat: 'wxfile://prepared/pattern_boat.webp',
      pattern_lighthouse: 'wxfile://prepared/pattern_lighthouse.webp',
    })
  })

  it('returns an empty subset and reports 100 percent immediately for no keys', async () => {
    const onProgress = vi.fn<(progress: GameImageLoadProgress) => void>()

    await expect(
      preloadGameImages([], {
        getImageInfo: vi.fn(),
        isCurrent: () => true,
        onProgress,
      })
    ).resolves.toEqual({})

    expect(onProgress).toHaveBeenCalledWith({ completed: 0, total: 0, percent: 100 })
  })

  it('deduplicates requested keys and returns exactly that requested subset', async () => {
    const requestedKeys = ['pattern_sun', 'pattern_coconut', 'pattern_sun'] as const
    const pathBySource = new Map([
      [gameImageRemoteUrl('pattern_sun'), 'wxfile://prepared/sun.webp'],
      [gameImageRemoteUrl('pattern_coconut'), 'wxfile://prepared/coconut.webp'],
    ])

    const result = await preloadGameImages(requestedKeys, {
      getImageInfo: async ({ src }) => ({ path: pathBySource.get(src) ?? '' }),
      isCurrent: () => true,
      onProgress: vi.fn(),
    })

    expect(result).toEqual({
      pattern_sun: 'wxfile://prepared/sun.webp',
      pattern_coconut: 'wxfile://prepared/coconut.webp',
    })
  })

  it('normalizes a non-positive concurrency to one active request', async () => {
    const controlled = createControlledImageInfo()
    const loading = preloadGameImages(['pattern_sun', 'pattern_coconut'], {
      getImageInfo: controlled.getImageInfo,
      isCurrent: () => true,
      onProgress: vi.fn(),
      concurrency: 0,
    })

    await flushWorkers()
    expect(controlled.active).toBe(1)
    expect(controlled.peak).toBe(1)

    resolveNext(controlled)
    await flushWorkers()
    expect(controlled.active).toBe(1)
    expect(controlled.peak).toBe(1)

    resolveNext(controlled)
    await expect(loading).resolves.toEqual({
      pattern_sun: 'wxfile://prepared/pattern_sun.webp',
      pattern_coconut: 'wxfile://prepared/pattern_coconut.webp',
    })
  })

  it('reports monotonic progress from zero to one hundred after every prepared image', async () => {
    const progress: GameImageLoadProgress[] = []

    await preloadGameImages(['pattern_sun', 'pattern_coconut', 'pattern_boat'], {
      getImageInfo: async ({ src }) => ({ path: `wxfile://prepared/${src.split('/').at(-1)}` }),
      isCurrent: () => true,
      onProgress: (update) => progress.push(update),
    })

    expect(progress).toEqual([
      { completed: 0, total: 3, percent: 0 },
      { completed: 1, total: 3, percent: 33 },
      { completed: 2, total: 3, percent: 67 },
      { completed: 3, total: 3, percent: 100 },
    ])
  })

  it('does not start queued images after one of three active requests fails', async () => {
    const controlled = createControlledImageInfo()
    const onProgress = vi.fn<(progress: GameImageLoadProgress) => void>()
    const loading = preloadGameImages(KEYS, {
      getImageInfo: controlled.getImageInfo,
      isCurrent: () => true,
      onProgress,
    })

    await flushWorkers()
    expect(controlled.startedKeys).toEqual(['pattern_sun', 'pattern_coconut', 'pattern_boat'])
    const failedRequest = controlled.pending.shift()
    const lateRequestOne = controlled.pending.shift()
    const lateRequestTwo = controlled.pending.shift()
    if (!failedRequest || !lateRequestOne || !lateRequestTwo) {
      throw new Error('expected three pending image requests')
    }

    const networkError = new Error('network unavailable')
    failedRequest.reject(networkError)
    await expect(loading).rejects.toBe(networkError)
    expect(onProgress).toHaveBeenCalledTimes(1)

    lateRequestOne.resolve({ path: 'wxfile://prepared/late-one.webp' })
    lateRequestTwo.resolve({ path: 'wxfile://prepared/late-two.webp' })
    await flushWorkers()
    expect(controlled.startedKeys).toEqual(['pattern_sun', 'pattern_coconut', 'pattern_boat'])
    expect(onProgress).toHaveBeenCalledTimes(1)
  })

  it('treats an undefined image-info rejection as terminal before a late worker settles', async () => {
    const controlled = createControlledImageInfo()
    const onProgress = vi.fn<(progress: GameImageLoadProgress) => void>()
    const loading = preloadGameImages(['pattern_sun', 'pattern_coconut'], {
      getImageInfo: controlled.getImageInfo,
      isCurrent: () => true,
      onProgress,
    })

    await flushWorkers()
    const failedRequest = controlled.pending.shift()
    const lateRequest = controlled.pending.shift()
    if (!failedRequest || !lateRequest) throw new Error('expected two pending image requests')

    failedRequest.reject(undefined)
    await expect(loading).rejects.toBeUndefined()

    lateRequest.resolve({ path: 'wxfile://prepared/late.webp' })
    await flushWorkers()
    expect(onProgress).toHaveBeenCalledTimes(1)
  })

  it('cancels before starting requests when the game session is already stale', async () => {
    const getImageInfo = vi.fn()

    await expect(
      preloadGameImages(['pattern_sun'], {
        getImageInfo,
        isCurrent: () => false,
        onProgress: vi.fn(),
      })
    ).rejects.toBeInstanceOf(GameImagePreloadCancelledError)

    expect(getImageInfo).not.toHaveBeenCalled()
  })

  it('cancels after an asynchronous completion without notifying stale progress', async () => {
    const controlled = createControlledImageInfo()
    const onProgress = vi.fn<(progress: GameImageLoadProgress) => void>()
    let current = true
    const loading = preloadGameImages(['pattern_sun'], {
      getImageInfo: controlled.getImageInfo,
      isCurrent: () => current,
      onProgress,
    })

    await flushWorkers()
    current = false
    resolveNext(controlled)

    await expect(loading).rejects.toBeInstanceOf(GameImagePreloadCancelledError)
    expect(onProgress).toHaveBeenCalledTimes(1)
  })

  it('normalizes an asynchronous failure that arrives after cancellation to the cancellation error', async () => {
    const controlled = createControlledImageInfo()
    let current = true
    const loading = preloadGameImages(['pattern_sun'], {
      getImageInfo: controlled.getImageInfo,
      isCurrent: () => current,
      onProgress: vi.fn(),
    })

    await flushWorkers()
    current = false
    const request = controlled.pending.shift()
    if (!request) throw new Error('expected a pending image request')
    request.reject(new Error('network unavailable'))

    await expect(loading).rejects.toBeInstanceOf(GameImagePreloadCancelledError)
  })

  it('cancels when the session becomes stale after a worker records a network failure', async () => {
    const controlled = createControlledImageInfo()
    const onProgress = vi.fn<(progress: GameImageLoadProgress) => void>()
    let current = true
    const loading = preloadGameImages(['pattern_sun'], {
      getImageInfo: controlled.getImageInfo,
      isCurrent: () => current,
      onProgress,
    })

    await flushWorkers()
    const request = controlled.pending.shift()
    if (!request) throw new Error('expected a pending image request')
    request.reject(new Error('network unavailable'))
    await Promise.resolve()
    current = false

    await expect(loading).rejects.toBeInstanceOf(GameImagePreloadCancelledError)
    expect(onProgress).toHaveBeenCalledTimes(1)
  })
})

describe('taroGetImageInfo', () => {
  it('uses the Taro image-info path as the prepared image path', async () => {
    taroMock.getImageInfo.mockResolvedValue({ path: 'wxfile://prepared/image.webp', width: 100, height: 100 })

    await expect(taroGetImageInfo({ src: 'https://cdn.example.com/image.webp' })).resolves.toEqual({
      path: 'wxfile://prepared/image.webp',
    })
    expect(taroMock.getImageInfo).toHaveBeenCalledWith({ src: 'https://cdn.example.com/image.webp' })
  })
})
