import { describe, expect, it, vi } from 'vitest'

import {
  MAX_SHOULDER_PRESS_SEGMENT_SIZE_BYTES,
  compressSavedShoulderPressSegment,
  shoulderPressCompressionScale
} from './compression'

describe('shoulder press segment compression', () => {
  it('caps portrait and landscape video at 720p without upscaling smaller video', () => {
    expect(shoulderPressCompressionScale(1080, 1920)).toBeCloseTo(2 / 3)
    expect(shoulderPressCompressionScale(1920, 1080)).toBeCloseTo(2 / 3)
    expect(shoulderPressCompressionScale(640, 480)).toBe(1)
  })

  it('compresses a persisted segment with fine-grained parameters and persists the result', async () => {
    const getVideoInfo = vi.fn()
      .mockResolvedValueOnce({
        duration: 30,
        size: 90_000,
        width: 1080,
        height: 1920
      })
      .mockResolvedValueOnce({
        duration: 30,
        size: 51_200,
        width: 720,
        height: 1280
      })
    const compressVideo = vi.fn().mockResolvedValue({
      tempFilePath: 'wxfile://tmp/compressed.mp4',
      size: 51_200
    })
    const saveFile = vi.fn().mockResolvedValue({
      savedFilePath: 'wxfile://store/compressed.mp4'
    })

    const result = await compressSavedShoulderPressSegment({
      rawSavedFilePath: 'wxfile://store/raw.mp4'
    }, {
      getVideoInfo,
      compressVideo,
      saveFile
    })

    expect(compressVideo).toHaveBeenCalledWith({
      src: 'wxfile://store/raw.mp4',
      bitrate: 2000,
      fps: 24,
      resolution: 2 / 3
    })
    expect(saveFile).toHaveBeenCalledWith({
      tempFilePath: 'wxfile://tmp/compressed.mp4'
    })
    expect(result).toEqual({
      savedFilePath: 'wxfile://store/compressed.mp4',
      durationMs: 30_000,
      sizeBytes: MAX_SHOULDER_PRESS_SEGMENT_SIZE_BYTES
    })
  })

  it('rejects a compressed segment larger than 50MB before persisting it', async () => {
    const saveFile = vi.fn()

    await expect(compressSavedShoulderPressSegment({
      rawSavedFilePath: 'wxfile://store/raw.mp4'
    }, {
      getVideoInfo: vi.fn()
        .mockResolvedValueOnce({
          duration: 30,
          size: 90_000,
          width: 1080,
          height: 1920
        })
        .mockResolvedValueOnce({
          duration: 30,
          size: 51_201,
          width: 720,
          height: 1280
        }),
      compressVideo: vi.fn().mockResolvedValue({
        tempFilePath: 'wxfile://tmp/compressed.mp4',
        size: 51_201
      }),
      saveFile
    })).rejects.toThrow('压缩后录像分段大小 52429824 字节超过 50MB 限制')

    expect(saveFile).not.toHaveBeenCalled()
  })
})
