import { fetchSignedAssetManifest } from '../../assets/signedAssetManifest'
import { isOfficialMotionSourceKey, type MotionSourceKey } from './catalog'

export function hasMotionInstructionAudio(sourceKey: unknown): sourceKey is MotionSourceKey {
  return isOfficialMotionSourceKey(sourceKey)
}

export async function getMotionInstructionAudioSrc(
  sourceKey: unknown,
  options?: { forceRefresh?: boolean },
): Promise<string | undefined> {
  if (!hasMotionInstructionAudio(sourceKey)) return undefined
  const manifest = await fetchSignedAssetManifest(options)
  return manifest.urls[sourceKey]
}
