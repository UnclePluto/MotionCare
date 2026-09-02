import { isOfficialMotionSourceKey, type MotionSourceKey } from './catalog'

import './assets/audio/instructions/motion-aerobic-high-knee.m4a'
import './assets/audio/instructions/motion-balance-sit-stand.m4a'
import './assets/audio/instructions/motion-resistance-row.m4a'
import './assets/audio/instructions/motion-resistance-leg-kickback.m4a'
import './assets/audio/instructions/motion-resistance-shoulder-press.m4a'

export const MOTION_INSTRUCTION_AUDIO_SRC: Record<MotionSourceKey, string> = {
  'motion-aerobic-high-knee': '/features/motion-training/assets/audio/instructions/motion-aerobic-high-knee.m4a',
  'motion-balance-sit-stand': '/features/motion-training/assets/audio/instructions/motion-balance-sit-stand.m4a',
  'motion-resistance-row': '/features/motion-training/assets/audio/instructions/motion-resistance-row.m4a',
  'motion-resistance-leg-kickback': '/features/motion-training/assets/audio/instructions/motion-resistance-leg-kickback.m4a',
  'motion-resistance-shoulder-press': '/features/motion-training/assets/audio/instructions/motion-resistance-shoulder-press.m4a',
}

export function getMotionInstructionAudioSrc(sourceKey: unknown): string | undefined {
  return isOfficialMotionSourceKey(sourceKey)
    ? MOTION_INSTRUCTION_AUDIO_SRC[sourceKey]
    : undefined
}
