import Taro from '@tarojs/taro'

export type GameAudioKey =
  | 'color_intro'
  | 'pattern_intro'
  | 'inhibition_intro'
  | 'category_intro'
  | 'sound_intro'
  | 'puzzle_intro'
  | 'count_3'
  | 'count_2'
  | 'count_1'
  | 'start'
  | 'correct'
  | 'wrong'
  | 'complete'
  | 'manual_end'
  | 'tap'

export type GameFeedbackKind = 'correct' | 'wrong'

export type GameFeedbackClip = {
  key: string
  text: string
  src: string
}

const AUDIO_MUTED_KEY = 'motioncare.gameAudioMuted'
const AUDIO_PLAYBACK_TIMEOUT_MS = 15_000

type GameAudioContext = ReturnType<typeof Taro.createInnerAudioContext> & {
  onPause?: (callback: () => void) => void
  onStop?: (callback: () => void) => void
  stop?: () => void
}

type ActiveGameAudioPlayback = {
  stop: () => void
}

const activeGameAudioPlaybacks = new Set<ActiveGameAudioPlayback>()

export type SoundDiscriminationAudioId =
  | 'bird_1'
  | 'bird_2'
  | 'bird_3'
  | 'train_1'
  | 'train_2'
  | 'phone_1'
  | 'phone_2'
  | 'phone_3'
  | 'laugh_1'
  | 'laugh_2'
  | 'laugh_3'
  | 'drum_1'
  | 'drum_2'
  | 'drum_3'

export type SoundDiscriminationCategory = 'bird' | 'train' | 'phone' | 'laugh' | 'drum'

export type SoundDiscriminationAudio = {
  id: SoundDiscriminationAudioId
  label: string
  category: SoundDiscriminationCategory
  imageKey: SoundDiscriminationCategory
  src: string
}

export const GAME_AUDIO_TEXT: Record<GameAudioKey, string> = {
  color_intro: '颜色顺序记忆训练开始。请记住方块亮起的顺序，随后按相同顺序点击。',
  pattern_intro: '图案顺序记忆训练开始。请记住图案出现的顺序，随后按相同顺序点击。',
  inhibition_intro: '反应抑制训练开始。请从数字中找出不一样的那个，并点击它。',
  category_intro: '分类切换训练开始。请根据当前提示，在不同分类规则之间切换并选择正确目标。',
  sound_intro: '声音辨别训练开始。请仔细听声音，并选择与声音相匹配的图片。',
  puzzle_intro: '拼图训练开始。请观察完整图像，将拼图块移动到正确位置。',
  count_3: '3',
  count_2: '2',
  count_1: '1',
  start: '开始',
  correct: '很好',
  wrong: '没关系',
  complete: '本次训练完成，辛苦了。',
  manual_end: '提前结束后，系统会保存一次部分完成记录。',
  tap: '',
}

export const GAME_AUDIO_SRC: Record<GameAudioKey, string> = {
  color_intro: '/pages/game-session/assets/audio/game-session/color_intro.m4a',
  pattern_intro: '/pages/game-session/assets/audio/game-session/pattern_intro.m4a',
  inhibition_intro: '/pages/game-session/assets/audio/game-session/inhibition_intro.m4a',
  category_intro: '/pages/game-session/assets/audio/game-session/category_intro.m4a',
  sound_intro: '/pages/game-session/assets/audio/game-session/sound_intro.m4a',
  puzzle_intro: '/pages/game-session/assets/audio/game-session/puzzle_intro.m4a',
  count_3: '/pages/game-session/assets/audio/game-session/count_3.m4a',
  count_2: '/pages/game-session/assets/audio/game-session/count_2.m4a',
  count_1: '/pages/game-session/assets/audio/game-session/count_1.m4a',
  start: '/pages/game-session/assets/audio/game-session/start.m4a',
  correct: '/pages/game-session/assets/audio/game-session/correct.m4a',
  wrong: '/pages/game-session/assets/audio/game-session/wrong.m4a',
  complete: '/pages/game-session/assets/audio/game-session/complete.m4a',
  manual_end: '/pages/game-session/assets/audio/game-session/manual_end.m4a',
  tap: '/pages/game-session/assets/audio/game-session/tap.m4a',
}

export const GAME_FEEDBACK: Record<GameFeedbackKind, GameFeedbackClip[]> = {
  correct: [
    { key: 'correct_1', text: '很好', src: '/pages/game-session/assets/audio/game-session/correct_1.m4a' },
    { key: 'correct_2', text: '答对啦', src: '/pages/game-session/assets/audio/game-session/correct_2.m4a' },
    { key: 'correct_3', text: '继续保持', src: '/pages/game-session/assets/audio/game-session/correct_3.m4a' },
    { key: 'correct_4', text: '反应很快', src: '/pages/game-session/assets/audio/game-session/correct_4.m4a' },
  ],
  wrong: [
    { key: 'wrong_1', text: '没关系', src: '/pages/game-session/assets/audio/game-session/wrong_1.m4a' },
    { key: 'wrong_2', text: '再试一题', src: '/pages/game-session/assets/audio/game-session/wrong_2.m4a' },
    { key: 'wrong_3', text: '慢慢来', src: '/pages/game-session/assets/audio/game-session/wrong_3.m4a' },
    { key: 'wrong_4', text: '调整一下', src: '/pages/game-session/assets/audio/game-session/wrong_4.m4a' },
  ],
}

export const SOUND_DISCRIMINATION_AUDIO: SoundDiscriminationAudio[] = [
  {
    id: 'bird_1',
    label: '小鸟1',
    category: 'bird',
    imageKey: 'bird',
    src: '/pages/game-session/assets/audio/sound-discrimination/bird_1.m4a',
  },
  {
    id: 'bird_2',
    label: '小鸟2',
    category: 'bird',
    imageKey: 'bird',
    src: '/pages/game-session/assets/audio/sound-discrimination/bird_2.m4a',
  },
  {
    id: 'bird_3',
    label: '小鸟3',
    category: 'bird',
    imageKey: 'bird',
    src: '/pages/game-session/assets/audio/sound-discrimination/bird_3.m4a',
  },
  {
    id: 'train_1',
    label: '火车汽笛声1',
    category: 'train',
    imageKey: 'train',
    src: '/pages/game-session/assets/audio/sound-discrimination/train_1.m4a',
  },
  {
    id: 'train_2',
    label: '火车汽笛声2',
    category: 'train',
    imageKey: 'train',
    src: '/pages/game-session/assets/audio/sound-discrimination/train_2.m4a',
  },
  {
    id: 'phone_1',
    label: '电话铃声1',
    category: 'phone',
    imageKey: 'phone',
    src: '/pages/game-session/assets/audio/sound-discrimination/phone_1.m4a',
  },
  {
    id: 'phone_2',
    label: '电话铃声2',
    category: 'phone',
    imageKey: 'phone',
    src: '/pages/game-session/assets/audio/sound-discrimination/phone_2.m4a',
  },
  {
    id: 'phone_3',
    label: '电话铃声3',
    category: 'phone',
    imageKey: 'phone',
    src: '/pages/game-session/assets/audio/sound-discrimination/phone_3.m4a',
  },
  {
    id: 'laugh_1',
    label: '笑声1',
    category: 'laugh',
    imageKey: 'laugh',
    src: '/pages/game-session/assets/audio/sound-discrimination/laugh_1.m4a',
  },
  {
    id: 'laugh_2',
    label: '笑声2',
    category: 'laugh',
    imageKey: 'laugh',
    src: '/pages/game-session/assets/audio/sound-discrimination/laugh_2.m4a',
  },
  {
    id: 'laugh_3',
    label: '笑声3',
    category: 'laugh',
    imageKey: 'laugh',
    src: '/pages/game-session/assets/audio/sound-discrimination/laugh_3.m4a',
  },
  {
    id: 'drum_1',
    label: '鼓1',
    category: 'drum',
    imageKey: 'drum',
    src: '/pages/game-session/assets/audio/sound-discrimination/drum_1.m4a',
  },
  {
    id: 'drum_2',
    label: '鼓2',
    category: 'drum',
    imageKey: 'drum',
    src: '/pages/game-session/assets/audio/sound-discrimination/drum_2.m4a',
  },
  {
    id: 'drum_3',
    label: '鼓3',
    category: 'drum',
    imageKey: 'drum',
    src: '/pages/game-session/assets/audio/sound-discrimination/drum_3.m4a',
  },
]

function pickIndex(length: number, random: () => number): number {
  const value = random()
  const normalized = Number.isFinite(value) ? Math.min(Math.max(value, 0), 0.9999999999999999) : 0
  return Math.floor(normalized * length)
}

export function pickGameFeedback(
  kind: GameFeedbackKind,
  random: () => number = Math.random
): GameFeedbackClip {
  const clips = GAME_FEEDBACK[kind]
  return clips[pickIndex(clips.length, random)]
}

export function isGameAudioMuted(): boolean {
  try {
    return Taro.getStorageSync(AUDIO_MUTED_KEY) === true
  } catch {
    return false
  }
}

export function setGameAudioMuted(value: boolean): void {
  try {
    Taro.setStorageSync(AUDIO_MUTED_KEY, value)
  } catch {
    // 本地偏好写入失败不应影响训练流程。
  }
  if (value) {
    stopActiveGameAudio()
  }
}

export function stopActiveGameAudio(): void {
  for (const playback of [...activeGameAudioPlaybacks]) {
    playback.stop()
  }
}

export function playGameAudio(key: GameAudioKey): Promise<void> {
  if (isGameAudioMuted()) return Promise.resolve()

  return playStaticAudio(GAME_AUDIO_SRC[key]).then(
    () => undefined,
    () => undefined
  )
}

export function playGameFeedback(
  kind: GameFeedbackKind,
  random: () => number = Math.random
): GameFeedbackClip {
  const feedback = pickGameFeedback(kind, random)
  if (!isGameAudioMuted()) {
    void playStaticAudio(feedback.src)
  }
  return feedback
}

function playStaticAudio(src: string): Promise<boolean> {
  return new Promise((resolve) => {
    let audio: GameAudioContext | undefined
    let timeout: ReturnType<typeof setTimeout> | undefined
    let playback: ActiveGameAudioPlayback | undefined
    let settled = false
    let forcedStop = false

    const finish = (ok: boolean) => {
      if (settled) return
      settled = true
      if (playback) {
        activeGameAudioPlaybacks.delete(playback)
      }
      if (timeout !== undefined) {
        clearTimeout(timeout)
      }
      try {
        audio?.destroy()
      } catch {
        // 播放失败或上下文状态异常时仍然 resolve，避免阻塞游戏。
      }
      resolve(ok)
    }

    try {
      audio = Taro.createInnerAudioContext() as GameAudioContext
      audio.src = src
      audio.onEnded(() => finish(true))
      audio.onError(() => finish(false))
      if (typeof audio.onStop === 'function') {
        audio.onStop(() => finish(!forcedStop))
      }
      if (typeof audio.onPause === 'function') {
        audio.onPause(() => finish(true))
      }
      timeout = setTimeout(() => finish(false), AUDIO_PLAYBACK_TIMEOUT_MS)
      playback = {
        stop: () => {
          if (settled) return
          forcedStop = true
          if (timeout !== undefined) {
            clearTimeout(timeout)
          }
          try {
            audio?.stop?.()
          } catch {
            // 停止失败时仍继续销毁，避免离页后残留播放。
          }
          finish(false)
        },
      }
      activeGameAudioPlaybacks.add(playback)
      audio.play()
    } catch {
      finish(false)
    }
  })
}

export function playAudioSrc(src: string): Promise<boolean> {
  if (isGameAudioMuted()) return Promise.resolve(false)
  return playStaticAudio(src)
}
