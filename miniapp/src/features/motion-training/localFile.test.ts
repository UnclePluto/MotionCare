import { describe, expect, it, vi } from 'vitest'

import { releaseMotionTrainingLocalFile, saveTemporaryMotionTrainingSegmentForRetry } from './localFile'

it('treats repeated file deletion as success but preserves real I/O failures', async () => {
  const fs = { unlink: vi.fn(options => options.fail({ errMsg: 'unlink:fail no such file or directory' })), removeSavedFile: vi.fn(options => options.success()) }
  expect(await releaseMotionTrainingLocalFile({ filePath: 'wxfile://temp/gone.mp4', localFileState: 'temporary' }, () => fs)).toBe(true)
  fs.unlink.mockImplementationOnce(options => options.fail({ errMsg: 'unlink:fail permission denied' }))
  expect(await releaseMotionTrainingLocalFile({ filePath: 'wxfile://temp/kept.mp4', localFileState: 'save_failed' }, () => fs)).toBe(false)
  expect(await releaseMotionTrainingLocalFile({ filePath: 'wxfile://store/saved.mp4', localFileState: 'saved' }, () => fs)).toBe(true)
  expect(fs.removeSavedFile).toHaveBeenCalledWith(expect.objectContaining({ filePath: 'wxfile://store/saved.mp4' }))
})

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

it('recovers legacy cleanup records without file kind using the saved-file removal API', async () => {
  let exists = true
  const fs = {
    unlink: vi.fn(options => options.fail({ errMsg: 'unlink:fail permission denied' })),
    removeSavedFile: vi.fn(options => { exists = false; options.success() })
  }
  expect(await releaseMotionTrainingLocalFile({ filePath: 'wxfile://store/legacy.mp4' }, () => fs)).toBe(true)
  expect(exists).toBe(false)
})

it.each(["unlink:fail file doesn't exist", 'unlink:fail file not exists'])('recognizes an expired WeChat path: %s', async errMsg => {
  const fs = { unlink: vi.fn(options => options.fail({ errMsg })), removeSavedFile: vi.fn() }
  expect(await releaseMotionTrainingLocalFile({ filePath: 'wxfile://temp/expired.mp4' }, () => fs)).toBe(true)
})

it('checks existence when iOS rejects deletion of an expired temporary path', async () => {
  const fs = {
    unlink: vi.fn(options => options.fail({ errMsg: 'unlink:fail permission denied' })),
    removeSavedFile: vi.fn(options => options.fail({ errMsg: 'removeSavedFile:fail invalid file' })),
    access: vi.fn(options => options.fail({ errMsg: 'access:fail no such file or directory' }))
  }
  expect(await releaseMotionTrainingLocalFile({ filePath: 'wxfile://tmp_expired.mp4' }, () => fs)).toBe(true)
  fs.access.mockImplementationOnce(options => options.success())
  expect(await releaseMotionTrainingLocalFile({ filePath: 'wxfile://tmp_exists.mp4' }, () => fs)).toBe(false)
  fs.access.mockImplementationOnce(options => options.fail({ errMsg: 'access:fail permission denied' }))
  expect(await releaseMotionTrainingLocalFile({ filePath: 'wxfile://tmp_unknown.mp4' }, () => fs)).toBe(false)
})
