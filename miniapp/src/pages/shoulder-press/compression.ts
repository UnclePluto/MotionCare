export const MAX_SHOULDER_PRESS_SEGMENT_SIZE_BYTES = 50 * 1024 * 1024
export const SHOULDER_PRESS_VIDEO_BITRATE_KBPS = 2000
export const SHOULDER_PRESS_VIDEO_FPS = 24

type ShoulderPressVideoInfo = {
  duration: number
  size: number
  width: number
  height: number
}

export type ShoulderPressCompressVideoOptions = {
  src: string
  bitrate: number
  fps: number
  resolution: number
}

type ShoulderPressCompressionDependencies = {
  getVideoInfo: (options: { src: string }) => Promise<ShoulderPressVideoInfo>
  compressVideo: (options: ShoulderPressCompressVideoOptions) => Promise<{
    tempFilePath: string
    size: number
  }>
  saveFile: (options: { tempFilePath: string }) => Promise<{
    savedFilePath?: string
  }>
}

export function shoulderPressCompressionScale(width: number, height: number): number {
  if (!Number.isFinite(width) || width <= 0 || !Number.isFinite(height) || height <= 0) {
    throw new Error('无法读取原始录像分辨率')
  }

  const isPortrait = height >= width
  const maxWidth = isPortrait ? 720 : 1280
  const maxHeight = isPortrait ? 1280 : 720
  return Math.min(1, maxWidth / width, maxHeight / height)
}

export async function compressSavedShoulderPressSegment(
  input: { rawSavedFilePath: string },
  dependencies: ShoulderPressCompressionDependencies
): Promise<{
    savedFilePath: string
    durationMs: number
    sizeBytes: number
  }> {
  const original = await dependencies.getVideoInfo({ src: input.rawSavedFilePath })
  const compressed = await dependencies.compressVideo({
    src: input.rawSavedFilePath,
    bitrate: SHOULDER_PRESS_VIDEO_BITRATE_KBPS,
    fps: SHOULDER_PRESS_VIDEO_FPS,
    resolution: shoulderPressCompressionScale(original.width, original.height)
  })
  const compressedInfo = await dependencies.getVideoInfo({ src: compressed.tempFilePath })
  const sizeBytes = Math.max(1, Math.round(compressedInfo.size * 1024))
  if (sizeBytes > MAX_SHOULDER_PRESS_SEGMENT_SIZE_BYTES) {
    throw new Error(`压缩后录像分段大小 ${sizeBytes} 字节超过 50MB 限制`)
  }

  const saved = await dependencies.saveFile({ tempFilePath: compressed.tempFilePath })
  if (!saved.savedFilePath) throw new Error('压缩录像持久化失败')

  return {
    savedFilePath: saved.savedFilePath,
    durationMs: Math.max(1, Math.round(compressedInfo.duration * 1000)),
    sizeBytes
  }
}
