import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const taroMock = vi.hoisted(() => ({
  createInnerAudioContext: vi.fn(),
}))

vi.mock('@tarojs/taro', () => ({
  default: taroMock,
}))

import {
  createShoulderPressAlertPlayer,
  SHOULDER_PRESS_ALERT_SRC,
  SHOULDER_PRESS_ALERT_TEXT,
} from './alertAudio'

function audioContextHarness() {
  const callbacks: { ended?: () => void; error?: () => void } = {}
  const audio = {
    src: '',
    destroy: vi.fn(),
    onEnded: vi.fn((callback: () => void) => {
      callbacks.ended = callback
    }),
    onError: vi.fn((callback: () => void) => {
      callbacks.error = callback
    }),
    play: vi.fn(),
    stop: vi.fn(),
  }

  return { audio, callbacks }
}

describe('shoulder press alert audio', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('uses the approved paused and recovered alert copy with local audio sources', () => {
    expect(SHOULDER_PRESS_ALERT_TEXT).toEqual({
      pause: '网络较慢，训练已暂停，请保持页面打开，等待视频上传。',
      ready: '视频上传已恢复，可以继续训练。',
    })
    expect(SHOULDER_PRESS_ALERT_SRC).toEqual({
      pause: '/pages/shoulder-press/assets/audio/network_slow_paused.m4a',
      ready: '/pages/shoulder-press/assets/audio/upload_recovered.m4a',
    })
  })

  it('resolves true after the alert ends and releases its audio context', async () => {
    const { audio, callbacks } = audioContextHarness()
    taroMock.createInnerAudioContext.mockReturnValue(audio)
    const player = createShoulderPressAlertPlayer()

    const playback = player.play('pause')
    callbacks.ended?.()

    await expect(playback).resolves.toBe(true)
    expect(audio.src).toBe('/pages/shoulder-press/assets/audio/network_slow_paused.m4a')
    expect(audio.destroy).toHaveBeenCalledTimes(1)
  })

  it('resolves false after an audio error and releases its context', async () => {
    const { audio, callbacks } = audioContextHarness()
    taroMock.createInnerAudioContext.mockReturnValue(audio)

    const playback = createShoulderPressAlertPlayer().play('ready')
    callbacks.error?.()

    await expect(playback).resolves.toBe(false)
    expect(audio.destroy).toHaveBeenCalledTimes(1)
  })

  it('does not start or retain a playback after onEnded fires during callback registration', async () => {
    const { audio } = audioContextHarness()
    audio.onEnded.mockImplementation((callback: () => void) => callback())
    taroMock.createInnerAudioContext.mockReturnValue(audio)

    const playback = createShoulderPressAlertPlayer().play('pause')

    await expect(playback).resolves.toBe(true)
    expect(audio.play).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
    expect(audio.destroy).toHaveBeenCalledTimes(1)
  })

  it('does not start or retain a playback after onError fires during callback registration', async () => {
    const { audio } = audioContextHarness()
    audio.onError.mockImplementation((callback: () => void) => callback())
    taroMock.createInnerAudioContext.mockReturnValue(audio)

    const playback = createShoulderPressAlertPlayer().play('ready')

    await expect(playback).resolves.toBe(false)
    expect(audio.play).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
    expect(audio.destroy).toHaveBeenCalledTimes(1)
  })

  it('resolves false when audio context construction throws', async () => {
    taroMock.createInnerAudioContext.mockImplementation(() => {
      throw new Error('audio unavailable')
    })

    await expect(createShoulderPressAlertPlayer().play('pause')).resolves.toBe(false)
  })

  it('times out after fifteen seconds when playback emits no terminal event', async () => {
    const { audio } = audioContextHarness()
    taroMock.createInnerAudioContext.mockReturnValue(audio)

    const playback = createShoulderPressAlertPlayer().play('pause')
    await vi.advanceTimersByTimeAsync(15_000)

    await expect(playback).resolves.toBe(false)
    expect(audio.destroy).toHaveBeenCalledTimes(1)
  })

  it('stops the previous alert before playing the next one', async () => {
    const first = audioContextHarness()
    const second = audioContextHarness()
    taroMock.createInnerAudioContext.mockReturnValueOnce(first.audio).mockReturnValueOnce(second.audio)
    const player = createShoulderPressAlertPlayer()

    const firstPlayback = player.play('pause')
    const secondPlayback = player.play('ready')

    await expect(firstPlayback).resolves.toBe(false)
    expect(first.audio.stop).toHaveBeenCalledTimes(1)
    expect(second.audio.src).toBe(SHOULDER_PRESS_ALERT_SRC.ready)
    expect(second.audio.play).toHaveBeenCalledTimes(1)
    second.callbacks.ended?.()
    await expect(secondPlayback).resolves.toBe(true)
  })

  it('keeps replacement playback false when stop synchronously emits ended', async () => {
    const first = audioContextHarness()
    const second = audioContextHarness()
    first.audio.stop.mockImplementation(() => first.callbacks.ended?.())
    taroMock.createInnerAudioContext.mockReturnValueOnce(first.audio).mockReturnValueOnce(second.audio)
    const player = createShoulderPressAlertPlayer()

    const firstPlayback = player.play('pause')
    const secondPlayback = player.play('ready')

    await expect(firstPlayback).resolves.toBe(false)
    second.callbacks.ended?.()
    await expect(secondPlayback).resolves.toBe(true)
  })

  it('stops and destroys the active alert when disposed', async () => {
    const { audio } = audioContextHarness()
    taroMock.createInnerAudioContext.mockReturnValue(audio)
    const player = createShoulderPressAlertPlayer()

    const playback = player.play('ready')
    player.dispose()

    await expect(playback).resolves.toBe(false)
    expect(audio.stop).toHaveBeenCalledTimes(1)
    expect(audio.destroy).toHaveBeenCalledTimes(1)
  })

  it('ignores late terminal callbacks after replacement has settled playback', async () => {
    const first = audioContextHarness()
    const second = audioContextHarness()
    taroMock.createInnerAudioContext.mockReturnValueOnce(first.audio).mockReturnValueOnce(second.audio)
    const player = createShoulderPressAlertPlayer()
    const firstPlayback = player.play('pause')

    void player.play('ready')
    first.callbacks.ended?.()
    first.callbacks.error?.()

    await expect(firstPlayback).resolves.toBe(false)
    expect(first.audio.destroy).toHaveBeenCalledTimes(1)
  })
})
