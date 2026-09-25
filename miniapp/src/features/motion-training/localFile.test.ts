import { describe, expect, it, vi } from 'vitest'

import { releaseMotionTrainingLocalFile, saveTemporaryMotionTrainingSegmentForRetry } from './localFile'

it('checks existence after an ambiguous delete failure before retiring a stale path', async () => {
  const fs = { unlink: vi.fn(options => options.fail({ errMsg: 'unlink:fail' })), removeSavedFile: vi.fn(),
    access: vi.fn(options => options.fail({ errMsg: 'access:fail no such file or directory' })) }
  expect(await releaseMotionTrainingLocalFile({ filePath: 'wxfile://old.mp4' }, () => fs)).toBe(true)
  expect(fs.access).toHaveBeenCalledWith(expect.objectContaining({ path: 'wxfile://old.mp4' }))
  fs.access.mockImplementationOnce(options => options.fail({ errMsg: 'access:fail permission denied' }))
  expect(await releaseMotionTrainingLocalFile({ filePath: 'wxfile://kept.mp4' }, () => fs)).toBe(false)
  fs.access.mockImplementationOnce(options => options.success())
  expect(await releaseMotionTrainingLocalFile({ filePath: 'wxfile://still-exists.mp4' }, () => fs)).toBe(false)
})

it('bounds a missing native callback and ignores its late success', async () => {
  vi.useFakeTimers()
  try {
    let complete!: () => void
    const onSuccess = vi.fn()
    const onError = vi.fn()
    const fs = { unlink: vi.fn(options => { complete = options.success }), removeSavedFile: vi.fn() }
    const pending = releaseMotionTrainingLocalFile({ filePath: 'wxfile://old.mp4', onError, onSuccess }, () => fs)
    await vi.advanceTimersByTimeAsync(10000)
    await expect(pending).resolves.toBe(false)
    complete()
    expect(onSuccess).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ errMsg: expect.stringContaining('timeout') }))
  } finally { vi.useRealTimers() }
})

it('reports native cleanup failures and isolates throwing diagnostic callbacks', async () => {
  const error = { errCode: 130001, errMsg: 'unlink:fail permission denied' }
  const onError = vi.fn(() => { throw new Error('diagnostic failed') })
  const fs = { unlink: vi.fn(options => options.fail(error)), removeSavedFile: vi.fn() }
  expect(await releaseMotionTrainingLocalFile({ filePath: 'private', onError }, () => fs)).toBe(false)
  expect(onError).toHaveBeenCalledWith(error)
})

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
