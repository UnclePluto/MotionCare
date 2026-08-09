import Taro from '@tarojs/taro'

export type ShoulderPressAlertKind = 'pause' | 'ready'

export const SHOULDER_PRESS_ALERT_TEXT: Record<ShoulderPressAlertKind, string> = {
  pause: '网络较慢，训练已暂停，请保持页面打开，等待视频上传。',
  ready: '视频上传已恢复，可以继续训练。',
}

export const SHOULDER_PRESS_ALERT_SRC: Record<ShoulderPressAlertKind, string> = {
  pause: '/pages/shoulder-press/assets/audio/network_slow_paused.m4a',
  ready: '/pages/shoulder-press/assets/audio/upload_recovered.m4a',
}

export type ShoulderPressAlertPlayer = {
  play: (kind: ShoulderPressAlertKind) => Promise<boolean>
  dispose: () => void
}

const ALERT_PLAYBACK_TIMEOUT_MS = 15_000

type AlertAudioContext = ReturnType<typeof Taro.createInnerAudioContext> & {
  stop?: () => void
}

type ActiveAlertPlayback = {
  stop: () => void
}

export function createShoulderPressAlertPlayer(): ShoulderPressAlertPlayer {
  let activePlayback: ActiveAlertPlayback | undefined

  const play = (kind: ShoulderPressAlertKind): Promise<boolean> => {
    activePlayback?.stop()

    return new Promise((resolve) => {
      let audio: AlertAudioContext | undefined
      let timeout: ReturnType<typeof setTimeout> | undefined
      let playback: ActiveAlertPlayback | undefined
      let settled = false

      const finish = (ok: boolean) => {
        if (settled) return
        settled = true
        if (timeout !== undefined) {
          clearTimeout(timeout)
        }
        if (activePlayback === playback) {
          activePlayback = undefined
        }
        try {
          audio?.destroy()
        } catch {
          // 上下文异常时仍需结束告警流程，避免阻塞训练。
        }
        resolve(ok)
      }

      try {
        audio = Taro.createInnerAudioContext() as AlertAudioContext
        audio.src = SHOULDER_PRESS_ALERT_SRC[kind]
        audio.onEnded(() => finish(true))
        audio.onError(() => finish(false))
        timeout = setTimeout(() => finish(false), ALERT_PLAYBACK_TIMEOUT_MS)
        playback = {
          stop: () => {
            if (settled) return
            try {
              audio?.stop?.()
            } catch {
              // 停止失败时仍继续销毁，避免残留语音。
            }
            finish(false)
          },
        }
        activePlayback = playback
        audio.play()
      } catch {
        finish(false)
      }
    })
  }

  return {
    play,
    dispose: () => activePlayback?.stop(),
  }
}
