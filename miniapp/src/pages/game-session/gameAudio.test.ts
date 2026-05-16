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
    expect(SOUND_DISCRIMINATION_AUDIO.bird_1).toMatchObject({
      id: 'bird_1',
      category: 'bird',
      imageKey: 'bird',
      src: '/assets/audio/sound-discrimination/bird_1.m4a',
    })
    expect(SOUND_DISCRIMINATION_AUDIO.phone_2).toMatchObject({
      id: 'phone_2',
      category: 'phone',
      imageKey: 'phone',
      src: '/assets/audio/sound-discrimination/phone_2.m4a',
    })
    expect(SOUND_DISCRIMINATION_AUDIO.drum_3).toMatchObject({
      id: 'drum_3',
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
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('resolves true when the mocked audio emits ended', async () => {
    let onEnded: (() => void) | undefined
    const audio = {
      destroy: vi.fn(),
      onEnded: vi.fn((callback: () => void) => {
        onEnded = callback
      }),
      onError: vi.fn(),
      play: vi.fn(),
      set src(_value: string) {},
    }
    taroMock.createInnerAudioContext.mockReturnValue(audio)

    const playback = playAudioSrc('/assets/audio/sound-discrimination/bird_1.m4a')
    onEnded?.()

    await expect(playback).resolves.toBe(true)
    expect(audio.destroy).toHaveBeenCalledTimes(1)
  })
})
