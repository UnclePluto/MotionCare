import { describe, expect, it, vi } from 'vitest'

import { saveTemporaryMotionTrainingSegmentForRetry } from './localFile'

describe('shoulder press failed segment persistence', () => {
  it('moves one temporary failed segment into saved storage', async () => {
    const saveFile = vi.fn().mockResolvedValue({
      savedFilePath: 'wxfile://store/segment-0.mp4'
    })

    await expect(saveTemporaryMotionTrainingSegmentForRetry({
      filePath: 'wxfile://temp/segment-0.mp4',
      localFileState: 'temporary'
    }, saveFile)).resolves.toEqual({
      filePath: 'wxfile://store/segment-0.mp4',
      localFileState: 'saved'
    })
  })

  it.each([null, undefined, { errMsg: 'saveFile:fail' }, { savedFilePath: '' }, { savedFilePath: 42 }])(
    'keeps the temporary recording when save returns an unusable response %j', async (response) => {
      await expect(saveTemporaryMotionTrainingSegmentForRetry({
        filePath: 'wxfile://temp/segment-0.mp4',
        localFileState: 'temporary'
      }, vi.fn().mockResolvedValue(response))).resolves.toEqual({
        filePath: 'wxfile://temp/segment-0.mp4',
        localFileState: 'save_failed'
      })
    }
  )

  it('does not retry persistent save after an earlier save failure', async () => {
    const saveFile = vi.fn()

    await expect(saveTemporaryMotionTrainingSegmentForRetry({
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

    await expect(saveTemporaryMotionTrainingSegmentForRetry({
      filePath: 'wxfile://temp/segment-0.mp4',
      localFileState: 'temporary'
    }, saveFile)).resolves.toEqual({
      filePath: 'wxfile://temp/segment-0.mp4',
      localFileState: 'save_failed'
    })
  })
})


it('reports native local save failure without replacing the temporary segment', async () => {
  const native = { errMsg: 'saveFile:fail storage full' }
  const onError = vi.fn()
  await expect(saveTemporaryMotionTrainingSegmentForRetry({ filePath: 'private.mp4', localFileState: 'temporary', onError }, () => Promise.reject(native))).resolves.toMatchObject({ localFileState: 'save_failed' })
  expect(onError).toHaveBeenCalledWith(native)
})
