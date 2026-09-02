import { staticAssetUrl } from '../../assets/staticAssetUrl'
import { OFFICIAL_MOTION_SOURCE_KEYS, isOfficialMotionSourceKey, type MotionSourceKey } from './catalog'
import { MOTION_INSTRUCTION_AUDIO_ASSET_PATHS } from './instructionAudioAssetManifest.generated'

export const MOTION_INSTRUCTION_AUDIO_SRC = Object.fromEntries(
  OFFICIAL_MOTION_SOURCE_KEYS.map((sourceKey) => [
    sourceKey,
    staticAssetUrl(MOTION_INSTRUCTION_AUDIO_ASSET_PATHS[sourceKey]),
  ]),
) as Record<MotionSourceKey, string>

export function getMotionInstructionAudioSrc(sourceKey: unknown): string | undefined {
  return isOfficialMotionSourceKey(sourceKey)
    ? MOTION_INSTRUCTION_AUDIO_SRC[sourceKey]
    : undefined
}
