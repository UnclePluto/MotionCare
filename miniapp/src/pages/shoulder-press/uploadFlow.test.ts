import { describe, expect, it, vi } from 'vitest'

import { runShoulderPressUploadFlow } from './uploadFlow'
import {
  loadShoulderPressSession,
  saveShoulderPressSession,
} from './session'

function createStorage() {
  const store = new Map<string, unknown>()
  return {
    getStorageSync: (key: string) => store.get(key),
    setStorageSync: (key: string, value: unknown) => store.set(key, value),
    removeStorageSync: (key: string) => store.delete(key),
  }
}

describe('肩部推举上传与处理流程', () => {
  it('排空分片后只 finish 一次并等待服务端自动处理', async () => {
    const storage = createStorage()
    saveShoulderPressSession(storage, {
      actionId: 42,
      videoId: 7,
      startedAt: 1,
      durationSeconds: 70,
      phase: 'uploading',
      segmentCount: 3,
      trainingDate: '2026-07-14',
      segments: [],
    })
    const finish = vi.fn().mockResolvedValue({ status: 'queued' })
    const getStatus = vi.fn()
      .mockResolvedValueOnce({ status: 'uploading', uploaded_segment_count: 3 })
      .mockResolvedValueOnce({ status: 'processing_failed', processing: { progress_percent: 70 } })
      .mockResolvedValueOnce({ status: 'attached', training_record_id: 99 })

    const result = await runShoulderPressUploadFlow({
      storage,
      drainSegments: vi.fn().mockResolvedValue(undefined),
      finish,
      getStatus,
      sleep: vi.fn().mockResolvedValue(undefined),
    })

    expect(finish).toHaveBeenCalledTimes(1)
    expect(getStatus).toHaveBeenCalledTimes(3)
    expect(result).toBe('succeeded')
    expect(loadShoulderPressSession(storage)).toBeNull()
  })

  it('本地分片未排空时不会提前 finish', async () => {
    const storage = createStorage()
    saveShoulderPressSession(storage, {
      actionId: 42,
      videoId: 7,
      startedAt: 1,
      durationSeconds: 30,
      phase: 'uploading',
      segmentCount: 1,
      trainingDate: '2026-07-14',
      segments: [{
        sequenceIndex: 0,
        savedFilePath: 'wxfile://segment.mp4',
        durationSeconds: 30,
        sizeBytes: 100,
        status: 'pending',
        retryCount: 0,
      }],
    })
    const finish = vi.fn().mockResolvedValue({ status: 'queued' })
    const drainSegments = vi.fn(async () => {
      const session = loadShoulderPressSession(storage)!
      saveShoulderPressSession(storage, { ...session, segments: [] })
    })

    await runShoulderPressUploadFlow({
      storage,
      drainSegments,
      finish,
      getStatus: vi.fn()
        .mockResolvedValueOnce({ status: 'uploading', uploaded_segment_count: 1 })
        .mockResolvedValueOnce({ status: 'attached', training_record_id: 99 }),
      sleep: vi.fn().mockResolvedValue(undefined),
    })

    expect(drainSegments).toHaveBeenCalled()
    expect(drainSegments.mock.invocationCallOrder[0]).toBeLessThan(
      finish.mock.invocationCallOrder[0],
    )
  })

  it('过期后提示重新训练并保留结果供页面展示', async () => {
    const storage = createStorage()
    saveShoulderPressSession(storage, {
      actionId: 42,
      videoId: 7,
      startedAt: 1,
      durationSeconds: 30,
      phase: 'processing',
      segmentCount: 1,
      trainingDate: '2026-07-14',
      segments: [],
    })

    const result = await runShoulderPressUploadFlow({
      storage,
      drainSegments: vi.fn(),
      finish: vi.fn(),
      getStatus: vi.fn().mockResolvedValue({ status: 'expired', training_record_id: null }),
      sleep: vi.fn(),
    })

    expect(result).toBe('expired')
    expect(loadShoulderPressSession(storage)).not.toBeNull()
  })

  it('本地分片持久化失败时不重复 finish', async () => {
    const storage = createStorage()
    saveShoulderPressSession(storage, {
      actionId: 42,
      videoId: 7,
      startedAt: 1,
      durationSeconds: 30,
      phase: 'uploading',
      segmentCount: 2,
      trainingDate: '2026-07-14',
      segments: [],
      unrecoverableReason: '录像分片保存失败',
    })
    const finish = vi.fn()

    const result = await runShoulderPressUploadFlow({
      storage,
      drainSegments: vi.fn(),
      finish,
      getStatus: vi.fn(),
      sleep: vi.fn(),
    })

    expect(result).toBe('unrecoverable')
    expect(finish).not.toHaveBeenCalled()
  })

  it('异常退出且没有有效分片时标记为不可恢复而不是服务端过期', async () => {
    const storage = createStorage()
    saveShoulderPressSession(storage, {
      actionId: 42,
      videoId: 7,
      startedAt: 1,
      durationSeconds: 0,
      phase: 'recording',
      segments: [],
    })

    const result = await runShoulderPressUploadFlow({
      storage,
      drainSegments: vi.fn(),
      finish: vi.fn(),
      getStatus: vi.fn(),
      sleep: vi.fn(),
    })

    expect(result).toBe('unrecoverable')
    expect(loadShoulderPressSession(storage)?.unrecoverableReason).toContain('有效录像分片')
  })

  it('服务端缺少分片且手机本地已无文件时停止自动重试', async () => {
    const storage = createStorage()
    saveShoulderPressSession(storage, {
      actionId: 42,
      videoId: 7,
      startedAt: 1,
      durationSeconds: 61,
      phase: 'uploading',
      segmentCount: 3,
      trainingDate: '2026-07-14',
      totalBytes: 300,
      uploadedBytes: 300,
      segments: [],
    })
    const finish = vi.fn()

    const result = await runShoulderPressUploadFlow({
      storage,
      drainSegments: vi.fn(),
      finish,
      getStatus: vi.fn().mockResolvedValue({
        status: 'uploading',
        uploaded_segment_count: 1,
      }),
      sleep: vi.fn(),
    })

    expect(result).toBe('unrecoverable')
    expect(finish).not.toHaveBeenCalled()
    expect(loadShoulderPressSession(storage)?.unrecoverableReason).toContain('服务端仅收到 1/3 个视频分片')
  })

  it('本地已进入处理阶段但服务端尚未 finish 时自动补交结束请求', async () => {
    const storage = createStorage()
    saveShoulderPressSession(storage, {
      actionId: 42,
      videoId: 7,
      startedAt: 1,
      durationSeconds: 30,
      phase: 'processing',
      segmentCount: 1,
      trainingDate: '2026-07-14',
      segments: [],
    })
    const finish = vi.fn().mockResolvedValue({ status: 'queued' })
    const getStatus = vi.fn()
      .mockResolvedValueOnce({ status: 'uploading', uploaded_segment_count: 1 })
      .mockResolvedValueOnce({ status: 'attached', training_record_id: 99 })

    const result = await runShoulderPressUploadFlow({
      storage,
      drainSegments: vi.fn(),
      finish,
      getStatus,
      sleep: vi.fn().mockResolvedValue(undefined),
    })

    expect(result).toBe('succeeded')
    expect(finish).toHaveBeenCalledTimes(1)
  })
})
