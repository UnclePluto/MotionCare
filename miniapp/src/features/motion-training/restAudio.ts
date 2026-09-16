import Taro from '@tarojs/taro'
import { fetchSignedAssetManifest, type StaticAssetKey } from '../../assets/signedAssetManifest'
import { createMotionTrainingAudioPlayer } from './alertAudio'

function numberParts(value: number): string[] {
  if (value < 10) return [String(value)]
  for (const [unit, name] of [[100000000, 'yi'], [10000, 'wan'], [1000, 'thousand'], [100, 'hundred'], [10, 'ten']] as const) {
    if (value < unit) continue
    const high = Math.floor(value / unit), low = value % unit
    return [...(unit === 10 && high === 1 ? [] : numberParts(high)), name,
      ...(low ? [...(low < unit / 10 ? ['0'] : []), ...numberParts(low)] : [])]
  }
  return []
}

export function createRestAudio(onFailure: () => void) {
  const voice = createMotionTrainingAudioPlayer({ timeoutMs: 15000 })
  let tick: ReturnType<typeof Taro.createInnerAudioContext> | undefined
  let deadline = 0, lastSecond = -1, generation = 0
  let visible = true, speaking = false
  const stopTick = () => { try { tick?.stop(); tick?.destroy() } catch { /* text remains usable */ } tick = undefined }
  const stopVoice = () => { generation++; speaking = false; try { voice.stop() } catch { /* isolated */ } }
  const playTick = async () => {
    if (!visible || speaking || Date.now() >= deadline || tick) return
    const own = generation
    try {
      const manifest = await fetchSignedAssetManifest()
      if (own !== generation || !visible || speaking || Date.now() >= deadline || tick) return
      tick = Taro.createInnerAudioContext(); tick.src = manifest.urls['motion-rest-tick']; tick.loop = true; tick.volume = 0.12
      tick.onError(() => { stopTick(); onFailure() }); tick.play()
    } catch { if (own === generation && visible) onFailure() }
  }
  const speak = async (parts: string[], valid: () => boolean) => {
    stopVoice(); stopTick()
    const own = generation; speaking = true
    try {
      const manifest = await fetchSignedAssetManifest()
      for (const part of parts) {
        if (own !== generation || !visible || !valid()) return
        const src = manifest.urls[`motion-rest-${part}` as StaticAssetKey]
        if (!src || !await voice.play(src)) { if (own === generation) onFailure(); return }
      }
    } catch { if (own === generation && visible) onFailure() }
    finally { if (own === generation) { speaking = false; void playTick() } }
  }
  return {
    begin(until: number, remainingSets: number) {
      deadline = until; lastSecond = Math.max(0, Math.ceil((deadline - Date.now()) / 1000))
      if (visible) void speak(['start', ...numberParts(remainingSets), 'sets'], () => Date.now() < deadline - 30000)
    },
    restore(until: number) { deadline = until; lastSecond = Math.max(0, Math.ceil((until - Date.now()) / 1000)); void playTick() },
    update() {
      if (!visible || !deadline) return
      const second = Math.max(0, Math.ceil((deadline - Date.now()) / 1000))
      if (second === lastSecond) return
      // A suspended timer must never replay cues that occurred while it was asleep.
      const contiguous = lastSecond - second === 1
      lastSecond = second
      if (!second) { stopTick(); if (contiguous) void speak(['ready'], () => Date.now() < deadline + 5000); else stopVoice() }
      else if (contiguous && (second === 30 || second <= 5)) {
        void speak([second === 30 ? 'thirty' : String(second)], () => Math.ceil((deadline - Date.now()) / 1000) === second)
      }
    },
    hide() { visible = false; stopVoice(); stopTick() },
    show() { visible = true; lastSecond = Math.max(0, Math.ceil((deadline - Date.now()) / 1000)); void playTick() },
    stop() { deadline = 0; stopVoice(); stopTick() },
    dispose() { visible = false; deadline = 0; stopVoice(); stopTick(); voice.dispose() }
  }
}
