import Taro from '@tarojs/taro'

export type GameAudioKey =
  | 'color_intro'
  | 'inhibition_intro'
  | 'count_3'
  | 'count_2'
  | 'count_1'
  | 'start'
  | 'correct'
  | 'wrong'
  | 'complete'
  | 'manual_end'
  | 'tap'

const AUDIO_MUTED_KEY = 'motioncare.gameAudioMuted'
const AUDIO_PLAYBACK_TIMEOUT_MS = 15_000

type GameAudioContext = ReturnType<typeof Taro.createInnerAudioContext> & {
  onPause?: (callback: () => void) => void
  onStop?: (callback: () => void) => void
}

export const GAME_AUDIO_TEXT: Record<GameAudioKey, string> = {
  color_intro: '请记住方块亮起的顺序，随后按相同顺序点击。',
  inhibition_intro: '请从数字中找出不一样的那个，并点击它。',
  count_3: '三',
  count_2: '二',
  count_1: '一',
  start: '开始',
  correct: '做得很好，答对了。',
  wrong: '没关系，调整一下，继续下一题。',
  complete: '本次训练完成，辛苦了。',
  manual_end: '提前结束后，系统会保存一次部分完成记录。',
  tap: '滴',
}

export const GAME_AUDIO_SRC: Record<GameAudioKey, string> = {
  color_intro: '/assets/audio/game-session/color_intro.m4a',
  inhibition_intro: '/assets/audio/game-session/inhibition_intro.m4a',
  count_3: '/assets/audio/game-session/count_3.m4a',
  count_2: '/assets/audio/game-session/count_2.m4a',
  count_1: '/assets/audio/game-session/count_1.m4a',
  start: '/assets/audio/game-session/start.m4a',
  correct: '/assets/audio/game-session/correct.m4a',
  wrong: '/assets/audio/game-session/wrong.m4a',
  complete: '/assets/audio/game-session/complete.m4a',
  manual_end: '/assets/audio/game-session/manual_end.m4a',
  tap: '/assets/audio/game-session/tap.m4a',
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
}

export function playGameAudio(key: GameAudioKey): Promise<void> {
  if (isGameAudioMuted()) return Promise.resolve()

  return new Promise((resolve) => {
    let audio: GameAudioContext | undefined
    let timeout: ReturnType<typeof setTimeout> | undefined
    let settled = false

    const finish = () => {
      if (settled) return
      settled = true
      if (timeout !== undefined) {
        clearTimeout(timeout)
      }
      try {
        audio?.destroy()
      } catch {
        // 播放失败或上下文状态异常时仍然 resolve，避免阻塞游戏。
      }
      resolve()
    }

    try {
      audio = Taro.createInnerAudioContext() as GameAudioContext
      audio.src = GAME_AUDIO_SRC[key]
      audio.onEnded(finish)
      audio.onError(finish)
      if (typeof audio.onStop === 'function') {
        audio.onStop(finish)
      }
      if (typeof audio.onPause === 'function') {
        audio.onPause(finish)
      }
      timeout = setTimeout(finish, AUDIO_PLAYBACK_TIMEOUT_MS)
      audio.play()
    } catch {
      finish()
    }
  })
}
