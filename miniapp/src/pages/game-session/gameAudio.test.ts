import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const taroMock = vi.hoisted(() => ({
  getStorageSync: vi.fn(),
  setStorageSync: vi.fn(),
  createInnerAudioContext: vi.fn(),
}))

vi.mock('@tarojs/taro', () => ({
  default: taroMock,
}))

import {
  GAME_AUDIO_SRC,
  GAME_AUDIO_TEXT,
  SOUND_DISCRIMINATION_AUDIO,
  isGameAudioMuted,
  playAudioSrc,
  playGameAudio,
  setGameAudioMuted,
} from './gameAudio'

function createMockAudio() {
  const callbacks: {
    ended?: () => void
    error?: () => void
    pause?: () => void
    stop?: () => void
  } = {}
  const audio = {
    src: '',
    destroy: vi.fn(),
    onEnded: vi.fn((callback: () => void) => {
      callbacks.ended = callback
    }),
    onError: vi.fn((callback: () => void) => {
      callbacks.error = callback
    }),
    onPause: vi.fn((callback: () => void) => {
      callbacks.pause = callback
    }),
    onStop: vi.fn((callback: () => void) => {
      callbacks.stop = callback
    }),
    play: vi.fn(),
  }

  return { audio, callbacks }
}

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
    const { audio } = createMockAudio()
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

describe('game audio catalog', () => {
  it('defines intro text and static sources for the remaining games', () => {
    expect(GAME_AUDIO_TEXT.pattern_intro).toContain('图案')
    expect(GAME_AUDIO_TEXT.category_intro).toContain('分类')
    expect(GAME_AUDIO_TEXT.sound_intro).toContain('声音')
    expect(GAME_AUDIO_TEXT.puzzle_intro).toContain('拼图')

    expect(GAME_AUDIO_SRC.pattern_intro).toBe('/assets/audio/game-session/pattern_intro.m4a')
    expect(GAME_AUDIO_SRC.category_intro).toBe('/assets/audio/game-session/category_intro.m4a')
    expect(GAME_AUDIO_SRC.sound_intro).toBe('/assets/audio/game-session/sound_intro.m4a')
    expect(GAME_AUDIO_SRC.puzzle_intro).toBe('/assets/audio/game-session/puzzle_intro.m4a')
  })

  it('defines sound discrimination clips with ascii static paths', () => {
    expect(Array.isArray(SOUND_DISCRIMINATION_AUDIO)).toBe(true)
    expect(SOUND_DISCRIMINATION_AUDIO).toHaveLength(14)
    expect(new Set(SOUND_DISCRIMINATION_AUDIO.map((item) => item.id)).size).toBe(SOUND_DISCRIMINATION_AUDIO.length)

    expect(SOUND_DISCRIMINATION_AUDIO.find((item) => item.id === 'bird_1')).toMatchObject({
      id: 'bird_1',
      label: '小鸟1',
      category: 'bird',
      imageKey: 'bird',
      src: '/assets/audio/sound-discrimination/bird_1.m4a',
    })
    expect(SOUND_DISCRIMINATION_AUDIO.find((item) => item.id === 'phone_2')).toMatchObject({
      id: 'phone_2',
      label: '电话铃声2',
      category: 'phone',
      imageKey: 'phone',
      src: '/assets/audio/sound-discrimination/phone_2.m4a',
    })
    expect(SOUND_DISCRIMINATION_AUDIO.find((item) => item.id === 'drum_3')).toMatchObject({
      id: 'drum_3',
      label: '鼓3',
      category: 'drum',
      imageKey: 'drum',
      src: '/assets/audio/sound-discrimination/drum_3.m4a',
    })
  })
})

describe('playAudioSrc', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    taroMock.getStorageSync.mockReturnValue(false)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('sets the provided static src and starts playback', () => {
    const { audio } = createMockAudio()
    taroMock.createInnerAudioContext.mockReturnValue(audio)

    void playAudioSrc('/assets/audio/sound-discrimination/bird_1.m4a')

    expect(audio.src).toBe('/assets/audio/sound-discrimination/bird_1.m4a')
    expect(audio.play).toHaveBeenCalledTimes(1)
  })

  it('resolves true when the mocked audio emits ended', async () => {
    const { audio, callbacks } = createMockAudio()
    taroMock.createInnerAudioContext.mockReturnValue(audio)

    const playback = playAudioSrc('/assets/audio/sound-discrimination/bird_1.m4a')
    callbacks.ended?.()

    await expect(playback).resolves.toBe(true)
    expect(audio.destroy).toHaveBeenCalledTimes(1)
  })

  it('resolves false when the mocked audio emits error', async () => {
    const { audio, callbacks } = createMockAudio()
    taroMock.createInnerAudioContext.mockReturnValue(audio)

    const playback = playAudioSrc('/assets/audio/sound-discrimination/bird_1.m4a')
    callbacks.error?.()

    await expect(playback).resolves.toBe(false)
    expect(audio.destroy).toHaveBeenCalledTimes(1)
  })

  it('resolves false when playback times out', async () => {
    const { audio } = createMockAudio()
    taroMock.createInnerAudioContext.mockReturnValue(audio)

    const playback = playAudioSrc('/assets/audio/sound-discrimination/bird_1.m4a')
    await vi.advanceTimersByTimeAsync(15_000)

    await expect(playback).resolves.toBe(false)
    expect(audio.destroy).toHaveBeenCalledTimes(1)
  })

  it('resolves true without creating audio context when muted', async () => {
    taroMock.getStorageSync.mockReturnValue(true)

    await expect(playAudioSrc('/assets/audio/sound-discrimination/bird_1.m4a')).resolves.toBe(true)
    expect(taroMock.createInnerAudioContext).not.toHaveBeenCalled()
  })
})
