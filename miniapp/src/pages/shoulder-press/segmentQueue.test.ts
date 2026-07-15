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
})
