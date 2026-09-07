import { mayRefreshSignedAssets } from '../../assets/signedAssetManifest'
import { createMotionTrainingAudioPlayer, type MotionTrainingAudioPlayer } from './alertAudio'
import { getMotionInstructionAudioSrc } from './instructionAudioManifest'

export type InstructionPlaybackResult = 'played' | 'failed' | 'cancelled'
export type InstructionPlayback = {
  play: (sourceKey: unknown) => Promise<InstructionPlaybackResult>
  stop: () => void
  dispose: () => void
}
export type InstructionPlaybackOptions = {
  player?: MotionTrainingAudioPlayer
  resolveSource?: typeof getMotionInstructionAudioSrc
  timeoutMs?: number
}

type PlaybackOperation = { finish: (result: InstructionPlaybackResult) => void }

export function createInstructionPlayback(
  options: InstructionPlaybackOptions = {},
): InstructionPlayback {
  const player = options.player ?? createMotionTrainingAudioPlayer({ timeoutMs: 90_000 })
  const resolveSource = options.resolveSource ?? getMotionInstructionAudioSrc
  const timeoutMs = options.timeoutMs ?? 90_000
  let active: PlaybackOperation | undefined
  let disposed = false

  const stop = () => active?.finish('cancelled')
  const play = (sourceKey: unknown): Promise<InstructionPlaybackResult> => {
    stop()
    if (disposed) return Promise.resolve('cancelled')

    return new Promise((resolve) => {
      let settled = false
      const finish = (result: InstructionPlaybackResult) => {
        if (settled) return
        // stop 可能立即触发底层播放结束；先结算，避免旧回调刷新或重播。
        settled = true
        clearTimeout(timer)
        if (active === operation) active = undefined
        try {
          player.stop()
        } catch {
          // 媒体清理异常不应阻塞取消、超时或页面导航。
        }
        resolve(result)
      }
      const operation = { finish }
      active = operation
      // 从签名请求开始计时，刷新和播放共享这一个总时限。
      const timer = setTimeout(() => finish('failed'), timeoutMs)

      const run = async () => {
        for (let attempt = 0; attempt < 2; attempt += 1) {
          if (settled) return
          try {
            const src = await resolveSource(sourceKey, attempt === 0 ? undefined : { forceRefresh: true })
            if (settled) return
            if (!src) { finish('failed'); return }
            const played = await player.play(src)
            if (settled) return
            if (played) { finish('played'); return }
          } catch (error) {
            if (settled) return
            if (!mayRefreshSignedAssets(error)) { finish('failed'); return }
          }
        }
        finish('failed')
      }
      void run()
    })
  }

  return {
    play,
    stop,
    dispose: () => {
      if (disposed) return
      disposed = true
      stop()
      player.dispose()
    },
  }
}
