import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PublicRequestError } from '../../api/client'
import { SignedAssetManifestError } from '../../assets/signedAssetManifest'
import { createInstructionPlayback } from './instructionPlayback'

const createPlayer = vi.hoisted(() => vi.fn())
vi.mock('@tarojs/taro', () => ({ default: {} }))
vi.mock('./alertAudio', () => ({ createMotionTrainingAudioPlayer: createPlayer }))

const sourceKey = 'motion-resistance-shoulder-press'
const signedSrc = 'https://cdn.example.com/voice.m4a?e=1&token=test'
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((ok, fail) => { resolve = ok; reject = fail })
  return { promise, resolve, reject }
}
function setup() {
  const player = { play: vi.fn().mockResolvedValue(true), stop: vi.fn(), dispose: vi.fn() }
  const resolveSource = vi.fn().mockResolvedValue(signedSrc)
  const controller = createInstructionPlayback({ player, resolveSource })
  return { player, resolveSource, controller }
}

describe('动作说明播放生命周期', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('默认播放器允许长说明播放并在成功后清理总计时器', async () => {
    const player = { play: vi.fn().mockResolvedValue(true), stop: vi.fn(), dispose: vi.fn() }
    createPlayer.mockReturnValue(player)
    const controller = createInstructionPlayback({ resolveSource: async () => signedSrc })
    await expect(controller.play(sourceKey)).resolves.toBe('played')
    expect(createPlayer).toHaveBeenCalledWith({ timeoutMs: 90_000 })
    expect(player.play).toHaveBeenCalledWith(signedSrc)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('停止后迟到的签名不会启动播放器', async () => {
    const { player, resolveSource, controller } = setup()
    const signing = deferred<string>()
    resolveSource.mockReturnValueOnce(signing.promise)
    const result = controller.play(sourceKey)
    controller.stop()
    await expect(result).resolves.toBe('cancelled')
    signing.resolve(signedSrc)
    await Promise.resolve()
    expect(player.play).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('90 秒包含等待签名时间，超时后不重试或播放迟到签名', async () => {
    const { player, resolveSource, controller } = setup()
    const signing = deferred<string>()
    resolveSource.mockReturnValueOnce(signing.promise)
    const result = controller.play(sourceKey)
    await vi.advanceTimersByTimeAsync(90_000)
    await expect(result).resolves.toBe('failed')
    signing.resolve(signedSrc)
    await Promise.resolve()
    expect(resolveSource).toHaveBeenCalledTimes(1)
    expect(player.play).not.toHaveBeenCalled()
  })

  it('60 秒取签名后播放只能再用 30 秒，stop 回调不会重试', async () => {
    const { player, resolveSource, controller } = setup()
    const signing = deferred<string>()
    const playback = deferred<boolean>()
    resolveSource.mockReturnValueOnce(signing.promise)
    player.play.mockReturnValueOnce(playback.promise)
    player.stop.mockImplementation(() => playback.resolve(false))
    const result = controller.play(sourceKey)
    await vi.advanceTimersByTimeAsync(60_000)
    signing.resolve(signedSrc)
    await vi.advanceTimersByTimeAsync(29_999)
    expect(player.play).toHaveBeenCalledOnce()
    const onFinish = vi.fn()
    void result.then(onFinish)
    await Promise.resolve()
    expect(onFinish).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    await expect(result).resolves.toBe('failed')
    expect(resolveSource).toHaveBeenCalledOnce()
    expect(player.stop).toHaveBeenCalled()
  })

  it('首播失败后强制刷新一次并成功播放', async () => {
    const { player, resolveSource, controller } = setup()
    player.play.mockResolvedValueOnce(false)
    resolveSource.mockResolvedValueOnce(signedSrc).mockResolvedValueOnce(signedSrc + '-fresh')
    await expect(controller.play(sourceKey)).resolves.toBe('played')
    expect(resolveSource.mock.calls).toEqual([[sourceKey, undefined], [sourceKey, { forceRefresh: true }]])
    expect(player.play.mock.calls).toEqual([[signedSrc], [signedSrc + '-fresh']])
  })

  it('两次播放失败即结束，不第三次刷新', async () => {
    const { player, resolveSource, controller } = setup()
    player.play.mockResolvedValue(false)
    await expect(controller.play(sourceKey)).resolves.toBe('failed')
    expect(player.play).toHaveBeenCalledTimes(2)
    expect(resolveSource).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each([429, 404])('签名 %s 直接失败', async (status) => {
    const { player, resolveSource, controller } = setup()
    resolveSource.mockRejectedValue(new PublicRequestError('签名失败', status))
    await expect(controller.play(sourceKey)).resolves.toBe('failed')
    expect(resolveSource).toHaveBeenCalledOnce()
    expect(player.play).not.toHaveBeenCalled()
  })

  it('不可信清单直接失败，网络异常最多重试一次', async () => {
    const { player, resolveSource, controller } = setup()
    resolveSource.mockRejectedValueOnce(new SignedAssetManifestError(false))
    await expect(controller.play(sourceKey)).resolves.toBe('failed')
    expect(resolveSource).toHaveBeenCalledOnce()
    expect(player.play).not.toHaveBeenCalled()
    resolveSource.mockReset().mockRejectedValue(new Error('网络不可用'))
    await expect(controller.play(sourceKey)).resolves.toBe('failed')
    expect(resolveSource.mock.calls).toEqual([[sourceKey, undefined], [sourceKey, { forceRefresh: true }]])
  })

  it('无音频地址直接失败', async () => {
    const { player, resolveSource, controller } = setup()
    resolveSource.mockResolvedValue(undefined)
    await expect(controller.play('unknown')).resolves.toBe('failed')
    expect(resolveSource).toHaveBeenCalledOnce()
    expect(player.play).not.toHaveBeenCalled()
  })

  it('连续 play 取消前次，旧请求失败不停止新播放', async () => {
    const { player, resolveSource, controller } = setup()
    const first = deferred<string>()
    const second = deferred<boolean>()
    resolveSource.mockReturnValueOnce(first.promise)
    player.play.mockReturnValueOnce(second.promise)
    const oldResult = controller.play(sourceKey)
    const newResult = controller.play('motion-resistance-row')
    await expect(oldResult).resolves.toBe('cancelled')
    await Promise.resolve()
    player.stop.mockClear()
    first.reject(new Error('旧请求失败'))
    await Promise.resolve()
    expect(player.stop).not.toHaveBeenCalled()
    expect(resolveSource).toHaveBeenCalledTimes(2)
    second.resolve(true)
    await expect(newResult).resolves.toBe('played')
  })

  it('dispose 及时取消并屏蔽迟到结果及之后的播放', async () => {
    const { player, resolveSource, controller } = setup()
    const signing = deferred<string>()
    resolveSource.mockReturnValueOnce(signing.promise)
    const result = controller.play(sourceKey)
    controller.dispose()
    await expect(result).resolves.toBe('cancelled')
    expect(player.dispose).toHaveBeenCalledOnce()
    signing.resolve(signedSrc)
    await Promise.resolve()
    await expect(controller.play(sourceKey)).resolves.toBe('cancelled')
    expect(player.play).not.toHaveBeenCalled()
    expect(resolveSource).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })
})
