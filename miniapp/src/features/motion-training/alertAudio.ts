import Taro from '@tarojs/taro'

import './assets/audio/network_slow_paused.m4a'
import './assets/audio/upload_recovered.m4a'

export type MotionTrainingAlertKind = 'pause' | 'ready'

export const MOTION_TRAINING_ALERT_TEXT: Record<MotionTrainingAlertKind, string> = {
  pause: '网络较慢，训练已暂停，请保持页面打开，等待视频上传。',
  ready: '视频上传已恢复，可以继续训练。',
}

export const MOTION_TRAINING_ALERT_SRC: Record<MotionTrainingAlertKind, string> = {
  pause: '/features/motion-training/assets/audio/network_slow_paused.m4a',
  ready: '/features/motion-training/assets/audio/upload_recovered.m4a',
}

export type MotionTrainingAlertPlayer = {
  play: (kind: MotionTrainingAlertKind) => Promise<boolean>
  dispose: () => void
}

export type MotionTrainingAudioPlayerOptions = {
  timeoutMs?: number
}

export type MotionTrainingAudioPlayer = {
  play: (src: string) => Promise<boolean>
  stop: () => void
  dispose: () => void
}

const DEFAULT_PLAYBACK_TIMEOUT_MS = 15_000

type MotionTrainingAudioContext = ReturnType<typeof Taro.createInnerAudioContext> & {
  stop?: () => void
}

type ActiveMotionTrainingPlayback = {
  stop: () => void
}

export function createMotionTrainingAudioPlayer(
  options: MotionTrainingAudioPlayerOptions = {},
): MotionTrainingAudioPlayer {
  let activePlayback: ActiveMotionTrainingPlayback | undefined
  const timeoutMs = options.timeoutMs ?? DEFAULT_PLAYBACK_TIMEOUT_MS

  const play = (src: string): Promise<boolean> => {
    activePlayback?.stop()

    return new Promise((resolve) => {
      let audio: MotionTrainingAudioContext | undefined
      let timeout: ReturnType<typeof setTimeout> | undefined
      let playback: ActiveMotionTrainingPlayback | undefined
      let settled = false

      const destroyAudio = () => {
        try {
          audio?.destroy()
        } catch {
          // 上下文异常时仍需结束告警流程，避免阻塞训练。
        }
      }

      const settle = (): boolean => {
        if (settled) return false
        settled = true
        if (timeout !== undefined) {
          clearTimeout(timeout)
        }
        if (activePlayback === playback) {
          activePlayback = undefined
        }
        return true
      }

      const finish = (ok: boolean) => {
        if (!settle()) return
        destroyAudio()
        resolve(ok)
      }

      try {
        audio = Taro.createInnerAudioContext() as MotionTrainingAudioContext
        audio.src = src
        playback = {
          stop: () => {
            if (!settle()) return
            try {
              audio?.stop?.()
            } catch {
              // 停止失败时仍继续销毁，避免残留语音。
            }
            destroyAudio()
            resolve(false)
          },
        }
        activePlayback = playback
        audio.onEnded(() => finish(true))
        if (settled) return
        audio.onError(() => finish(false))
        if (settled) return
        timeout = setTimeout(() => finish(false), timeoutMs)
        if (settled) return
        audio.play()
      } catch {
        finish(false)
      }
    })
  }

  return {
    play,
    stop: () => activePlayback?.stop(),
    dispose: () => activePlayback?.stop(),
  }
}

export function createMotionTrainingAlertPlayer(): MotionTrainingAlertPlayer {
  const player = createMotionTrainingAudioPlayer({ timeoutMs: 15_000 })

  return {
    play: (kind) => player.play(MOTION_TRAINING_ALERT_SRC[kind]),
    dispose: player.dispose,
  }
}
