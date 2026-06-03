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
  GAME_FEEDBACK,
  SOUND_DISCRIMINATION_AUDIO,
  pickGameFeedback,
  isGameAudioMuted,
  playAudioSrc,
  playGameAudio,
  playGameFeedback,
  setGameAudioMuted,
  stopActiveGameAudio,
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
    stop: vi.fn(),
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

  it('plays the selected feedback clip and returns its text', () => {
    const { audio } = createMockAudio()
    taroMock.getStorageSync.mockReturnValue(false)
    taroMock.createInnerAudioContext.mockReturnValue(audio)

    const feedback = playGameFeedback('wrong', () => 0)

    expect(feedback.text).toBe('没关系')
    expect(audio.src).toBe('/pages/game-session/assets/audio/game-session/wrong_1.m4a')
    expect(audio.play).toHaveBeenCalledTimes(1)
  })
})

describe('game audio catalog', () => {
  it('defines intro text and static sources for the remaining games', () => {
    expect(GAME_AUDIO_TEXT.pattern_intro).toContain('图案')
    expect(GAME_AUDIO_TEXT.category_intro).toContain('分类')
    expect(GAME_AUDIO_TEXT.sound_intro).toContain('声音')
    expect(GAME_AUDIO_TEXT.puzzle_intro).toContain('拼图')

    expect(GAME_AUDIO_SRC.pattern_intro).toBe('/pages/game-session/assets/audio/game-session/pattern_intro.m4a')
    expect(GAME_AUDIO_SRC.category_intro).toBe('/pages/game-session/assets/audio/game-session/category_intro.m4a')
    expect(GAME_AUDIO_SRC.sound_intro).toBe('/pages/game-session/assets/audio/game-session/sound_intro.m4a')
    expect(GAME_AUDIO_SRC.puzzle_intro).toBe('/pages/game-session/assets/audio/game-session/puzzle_intro.m4a')
  })

  it('uses a non-voice UI sound for tap feedback', () => {
    expect(GAME_AUDIO_TEXT.tap).toBe('')
    expect(GAME_AUDIO_SRC.tap).toBe('/pages/game-session/assets/audio/game-session/tap.m4a')
  })

  it('uses Arabic numerals for countdown text', () => {
    expect(GAME_AUDIO_TEXT.count_3).toBe('3')
    expect(GAME_AUDIO_TEXT.count_2).toBe('2')
    expect(GAME_AUDIO_TEXT.count_1).toBe('1')
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
      src: '/pages/game-session/assets/audio/sound-discrimination/bird_1.m4a',
    })
    expect(SOUND_DISCRIMINATION_AUDIO.find((item) => item.id === 'phone_2')).toMatchObject({
      id: 'phone_2',
      label: '电话铃声2',
      category: 'phone',
      imageKey: 'phone',
      src: '/pages/game-session/assets/audio/sound-discrimination/phone_2.m4a',
    })
    expect(SOUND_DISCRIMINATION_AUDIO.find((item) => item.id === 'drum_3')).toMatchObject({
      id: 'drum_3',
      label: '鼓3',
      category: 'drum',
      imageKey: 'drum',
      src: '/pages/game-session/assets/audio/sound-discrimination/drum_3.m4a',
    })
  })
})

describe('game feedback catalog', () => {
  it('defines short varied feedback clips', () => {
    expect(GAME_FEEDBACK.correct.map((item) => item.text)).toEqual([
      '很好',
      '答对啦',
      '继续保持',
      '反应很快',
    ])
    expect(GAME_FEEDBACK.wrong.map((item) => item.text)).toEqual([
      '没关系',
      '再试一题',
      '慢慢来',
      '调整一下',
    ])
    expect(GAME_FEEDBACK.correct.every((item) => item.src.endsWith('.m4a'))).toBe(true)
    expect(GAME_FEEDBACK.wrong.every((item) => item.src.endsWith('.m4a'))).toBe(true)
  })

  it('selects feedback deterministically when random is injected', () => {
    expect(pickGameFeedback('correct', () => 0).text).toBe('很好')
    expect(pickGameFeedback('correct', () => 0.74).text).toBe('继续保持')
    expect(pickGameFeedback('wrong', () => 0.99).text).toBe('调整一下')
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

    void playAudioSrc('/pages/game-session/assets/audio/sound-discrimination/bird_1.m4a')

    expect(audio.src).toBe('/pages/game-session/assets/audio/sound-discrimination/bird_1.m4a')
    expect(audio.play).toHaveBeenCalledTimes(1)
  })

  it('resolves true when the mocked audio emits ended', async () => {
    const { audio, callbacks } = createMockAudio()
    taroMock.createInnerAudioContext.mockReturnValue(audio)

    const playback = playAudioSrc('/pages/game-session/assets/audio/sound-discrimination/bird_1.m4a')
    callbacks.ended?.()

    await expect(playback).resolves.toBe(true)
    expect(audio.destroy).toHaveBeenCalledTimes(1)
  })

  it('resolves false when the mocked audio emits error', async () => {
    const { audio, callbacks } = createMockAudio()
    taroMock.createInnerAudioContext.mockReturnValue(audio)

    const playback = playAudioSrc('/pages/game-session/assets/audio/sound-discrimination/bird_1.m4a')
    callbacks.error?.()

    await expect(playback).resolves.toBe(false)
    expect(audio.destroy).toHaveBeenCalledTimes(1)
  })

  it('resolves false when playback times out', async () => {
    const { audio } = createMockAudio()
    taroMock.createInnerAudioContext.mockReturnValue(audio)

    const playback = playAudioSrc('/pages/game-session/assets/audio/sound-discrimination/bird_1.m4a')
    await vi.advanceTimersByTimeAsync(15_000)

    await expect(playback).resolves.toBe(false)
    expect(audio.destroy).toHaveBeenCalledTimes(1)
  })

  it('resolves false without creating audio context when muted', async () => {
    taroMock.getStorageSync.mockReturnValue(true)

    await expect(playAudioSrc('/pages/game-session/assets/audio/sound-discrimination/bird_1.m4a')).resolves.toBe(false)
    expect(taroMock.createInnerAudioContext).not.toHaveBeenCalled()
  })

  it('stops active playback when muting audio', async () => {
    const { audio } = createMockAudio()
    taroMock.createInnerAudioContext.mockReturnValue(audio)

    const playback = playAudioSrc('/pages/game-session/assets/audio/sound-discrimination/bird_1.m4a')
    setGameAudioMuted(true)

    await expect(playback).resolves.toBe(false)
    expect(audio.stop).toHaveBeenCalledTimes(1)
    expect(audio.destroy).toHaveBeenCalledTimes(1)
  })

  it('stops all active playback on demand', async () => {
    const first = createMockAudio()
    const second = createMockAudio()
    taroMock.createInnerAudioContext.mockReturnValueOnce(first.audio).mockReturnValueOnce(second.audio)

    const firstPlayback = playAudioSrc('/pages/game-session/assets/audio/sound-discrimination/bird_1.m4a')
    const secondPlayback = playAudioSrc('/pages/game-session/assets/audio/sound-discrimination/bird_2.m4a')

    stopActiveGameAudio()

    await expect(firstPlayback).resolves.toBe(false)
    await expect(secondPlayback).resolves.toBe(false)
    expect(first.audio.stop).toHaveBeenCalledTimes(1)
    expect(second.audio.stop).toHaveBeenCalledTimes(1)
  })
})
