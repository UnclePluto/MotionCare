import { describe, expect, it, vi } from 'vitest'

import { SegmentQueueRunner } from './segmentQueue'
import { loadShoulderPressSession, saveShoulderPressSession } from './session'

function storageWithSegment() {
  const store = new Map<string, unknown>()
  const storage = {
    getStorageSync: (key: string) => store.get(key),
    setStorageSync: (key: string, value: unknown) => store.set(key, value),
    removeStorageSync: (key: string) => store.delete(key),
  }
  saveShoulderPressSession(storage, {
    actionId: 42,
    videoId: 7,
    startedAt: 1,
    durationSeconds: 30,
    phase: 'recording',
    totalBytes: 100,
    uploadedBytes: 0,
    segments: [{
      sequenceIndex: 0,
      savedFilePath: 'wxfile://saved-0.mp4',
      durationSeconds: 30,
      sizeBytes: 100,
      status: 'pending',
      retryCount: 0,
    }],
  })
  return { storage }
}

describe('肩部推举分片重试队列', () => {
  it('业务服务器确认后删除手机文件并移出队列', async () => {
    const { storage } = storageWithSegment()
    const upload = vi.fn().mockResolvedValue({ object_hash: 'hash' })
    const removeFile = vi.fn().mockResolvedValue(undefined)
    const runner = new SegmentQueueRunner({ storage, upload, removeFile })

    await runner.runNext()

    expect(upload).toHaveBeenCalledTimes(1)
    expect(removeFile).toHaveBeenCalledWith('wxfile://saved-0.mp4')
    expect(loadShoulderPressSession(storage)?.segments).toEqual([])
    expect(loadShoulderPressSession(storage)?.uploadedBytes).toBe(100)
  })

  it('上传失败保留文件并写入递增退避时间', async () => {
    const { storage } = storageWithSegment()
    const upload = vi.fn().mockRejectedValue(new Error('network'))
    const removeFile = vi.fn()
    const runner = new SegmentQueueRunner({
      storage,
      upload,
      removeFile,
      now: () => 1_000,
    })

    await runner.runNext()

    const segment = loadShoulderPressSession(storage)?.segments[0]
    expect(segment).toEqual(expect.objectContaining({
      status: 'retrying',
      retryCount: 1,
      lastError: 'network',
    }))
    expect(segment?.nextRetryAt).toBeGreaterThan(1_000)
    expect(removeFile).not.toHaveBeenCalled()
  })

  it('同一 runner 始终保持单上传并发', async () => {
    const { storage } = storageWithSegment()
    let resolveUpload: (value: unknown) => void = () => undefined
    const upload = vi.fn(() => new Promise((resolve) => { resolveUpload = resolve }))
    const runner = new SegmentQueueRunner({
      storage,
      upload,
      removeFile: vi.fn().mockResolvedValue(undefined),
    })

    const first = runner.runNext()
    const second = runner.runNext()
    expect(upload).toHaveBeenCalledTimes(1)
    resolveUpload({ object_hash: 'hash' })
    await Promise.all([first, second])
  })

  it('摄像页与上传页的不同 runner 也不会重复上传同一分片', async () => {
    const { storage } = storageWithSegment()
    let resolveUpload: (value: unknown) => void = () => undefined
    const upload = vi.fn(() => new Promise((resolve) => { resolveUpload = resolve }))
    const options = {
      storage,
      upload,
      removeFile: vi.fn().mockResolvedValue(undefined),
    }
    const cameraRunner = new SegmentQueueRunner(options)
    const uploadRunner = new SegmentQueueRunner(options)

    const fromCamera = cameraRunner.runNext()
    const fromUploadPage = uploadRunner.runNext()
    expect(upload).toHaveBeenCalledTimes(1)
    resolveUpload({ object_hash: 'hash' })
    await Promise.all([fromCamera, fromUploadPage])
  })

  it('服务端确认后本地删除失败时不会重复上传', async () => {
    const { storage } = storageWithSegment()
    const upload = vi.fn().mockResolvedValue({ object_hash: 'hash' })
    const removeFile = vi.fn()
      .mockRejectedValueOnce(new Error('unlink failed'))
      .mockResolvedValueOnce(undefined)
    const runner = new SegmentQueueRunner({ storage, upload, removeFile })

    await runner.runNext()
    expect(loadShoulderPressSession(storage)?.segments[0]?.status).toBe('confirmed')

    await runner.runNext()

    expect(upload).toHaveBeenCalledTimes(1)
    expect(removeFile).toHaveBeenCalledTimes(2)
    expect(loadShoulderPressSession(storage)?.segments).toEqual([])
  })

  it('把当前分片的真实上传进度透传给页面', async () => {
    const { storage } = storageWithSegment()
    const onProgress = vi.fn()
    const timestamps = [0, 1_000, 2_000, 2_500]
    const upload = vi.fn(async ({ onProgress: reportProgress }) => {
      reportProgress?.({
        progress: 37,
        totalBytesSent: 37,
        totalBytesExpectedToSend: 100,
      })
      reportProgress?.({
        progress: 100,
        totalBytesSent: 100,
        totalBytesExpectedToSend: 100,
      })
      return { object_hash: 'hash' }
    })
    const runner = new SegmentQueueRunner({
      storage,
      upload,
      removeFile: vi.fn().mockResolvedValue(undefined),
      onProgress,
      now: () => timestamps.shift() ?? 2_500,
    })

    await runner.runNext()

    expect(onProgress).toHaveBeenNthCalledWith(1, {
      sequenceIndex: 0,
      progress: 37,
      uploadedBytes: 37,
      totalBytes: 100,
      bytesPerSecond: 37,
    })
    expect(onProgress).toHaveBeenNthCalledWith(2, {
      sequenceIndex: 0,
      progress: 100,
      uploadedBytes: 100,
      totalBytes: 100,
      bytesPerSecond: 126,
    })
  })

  it('微信没有触发中间进度事件时用请求耗时生成最终速度', async () => {
    const { storage } = storageWithSegment()
    const onProgress = vi.fn()
    const timestamps = [0, 1_000, 3_000]
    const runner = new SegmentQueueRunner({
      storage,
      upload: vi.fn().mockResolvedValue({ object_hash: 'hash' }),
      removeFile: vi.fn().mockResolvedValue(undefined),
      onProgress,
      now: () => timestamps.shift() ?? 3_000,
    })

    await runner.runNext()

    expect(onProgress).toHaveBeenCalledWith({
      sequenceIndex: 0,
      progress: 100,
      uploadedBytes: 100,
      totalBytes: 100,
      bytesPerSecond: 50,
    })
  })
})
