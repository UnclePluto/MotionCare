import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const taroMock = vi.hoisted(() => ({
  getStorageSync: vi.fn(),
  setStorageSync: vi.fn(),
  createInnerAudioContext: vi.fn(),
}))

vi.mock('@tarojs/taro', () => ({
  default: taroMock,
}))

import { isGameAudioMuted, playGameAudio, setGameAudioMuted } from './gameAudio'

describe('game audio preferences', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('treats storage read failures as unmuted', () => {
    taroMock.getStorageSync.mockImplementation(() => {
      throw new Error('storage unavailable')
    })

    expect(isGameAudioMuted()).toBe(false)
  })

  it('ignores storage write failures', () => {
    taroMock.setStorageSync.mockImplementation(() => {
      throw new Error('storage unavailable')
    })

    expect(() => setGameAudioMuted(true)).not.toThrow()
  })
})

describe('playGameAudio', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    taroMock.getStorageSync.mockReturnValue(false)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('resolves and destroys the context when playback never emits terminal events', async () => {
    const audio = {
      destroy: vi.fn(),
      onEnded: vi.fn(),
      onError: vi.fn(),
      play: vi.fn(),
      set src(_value: string) {},
    }
    taroMock.createInnerAudioContext.mockReturnValue(audio)

    const playback = playGameAudio('start')
    await vi.advanceTimersByTimeAsync(15_000)

    await expect(playback).resolves.toBeUndefined()
    expect(audio.destroy).toHaveBeenCalledTimes(1)
  })

  it('resolves when audio context creation fails', async () => {
    taroMock.createInnerAudioContext.mockImplementation(() => {
      throw new Error('audio unavailable')
    })

    await expect(playGameAudio('start')).resolves.toBeUndefined()
  })
})
