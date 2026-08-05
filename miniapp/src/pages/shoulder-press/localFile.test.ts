import { describe, expect, it, vi } from 'vitest'

import { saveTemporaryShoulderPressSegmentForRetry } from './localFile'

describe('shoulder press failed segment persistence', () => {
  it('moves one temporary failed segment into saved storage', async () => {
    const saveFile = vi.fn().mockResolvedValue({
      savedFilePath: 'wxfile://store/segment-0.mp4'
    })

    await expect(saveTemporaryShoulderPressSegmentForRetry({
      filePath: 'wxfile://temp/segment-0.mp4',
      localFileState: 'temporary'
    }, saveFile)).resolves.toEqual({
      filePath: 'wxfile://store/segment-0.mp4',
      localFileState: 'saved'
    })
  })

  it('does not retry persistent save after an earlier save failure', async () => {
    const saveFile = vi.fn()

    await expect(saveTemporaryShoulderPressSegmentForRetry({
      filePath: 'wxfile://temp/segment-0.mp4',
      localFileState: 'save_failed'
    }, saveFile)).resolves.toEqual({
      filePath: 'wxfile://temp/segment-0.mp4',
      localFileState: 'save_failed'
    })
    expect(saveFile).not.toHaveBeenCalled()
  })

  it('keeps the temporary path and records a failed save result', async () => {
    const saveFile = vi.fn().mockRejectedValue(new Error('storage full'))

    await expect(saveTemporaryShoulderPressSegmentForRetry({
      filePath: 'wxfile://temp/segment-0.mp4',
      localFileState: 'temporary'
    }, saveFile)).resolves.toEqual({
      filePath: 'wxfile://temp/segment-0.mp4',
      localFileState: 'save_failed'
    })
  })
})
