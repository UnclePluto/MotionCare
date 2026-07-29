import { describe, expect, it, vi } from 'vitest'

import { startCameraRecordingWithRetry } from './cameraRecording'

describe('微信摄像头录像启动', () => {
  it('分片轮转启动失败时按顺序重试并保留超时回调', async () => {
    const timeoutCallback = vi.fn()
    const sleep = vi.fn().mockResolvedValue(undefined)
    let attempts = 0
    let latestTimeout: ((result: { tempVideoPath: string }) => void) | undefined
    const startRecord = vi.fn((options) => {
      attempts += 1
      latestTimeout = options.timeoutCallback
      if (attempts < 3) options.fail({ errMsg: 'camera is still stopping' })
      else options.success()
    })

    await startCameraRecordingWithRetry({
      startRecord,
      timeoutCallback,
      retryDelaysMs: [200, 500, 1_000],
      sleep,
      isCancelled: () => false,
    })
    latestTimeout?.({ tempVideoPath: 'wxfile://segment-1.mp4' })

    expect(startRecord).toHaveBeenCalledTimes(3)
    expect(sleep).toHaveBeenNthCalledWith(1, 200)
    expect(sleep).toHaveBeenNthCalledWith(2, 500)
    expect(timeoutCallback).toHaveBeenCalledWith({
      tempVideoPath: 'wxfile://segment-1.mp4',
    })
  })

  it('重试耗尽后抛出最后一次摄像头错误用于兜底收尾', async () => {
    const startRecord = vi.fn((options) => {
      options.fail({ errMsg: 'startRecord failed' })
    })

    await expect(startCameraRecordingWithRetry({
      startRecord,
      timeoutCallback: vi.fn(),
      retryDelaysMs: [200, 500],
      sleep: vi.fn().mockResolvedValue(undefined),
      isCancelled: () => false,
    })).rejects.toThrow('startRecord failed')
    expect(startRecord).toHaveBeenCalledTimes(3)
  })

  it('页面隐藏后不再发起下一次重试', async () => {
    let cancelled = false
    const startRecord = vi.fn((options) => {
      cancelled = true
      options.fail({ errMsg: 'startRecord failed' })
    })

    await expect(startCameraRecordingWithRetry({
      startRecord,
      timeoutCallback: vi.fn(),
      retryDelaysMs: [200, 500],
      sleep: vi.fn().mockResolvedValue(undefined),
      isCancelled: () => cancelled,
    })).rejects.toThrow('录像启动已取消')
    expect(startRecord).toHaveBeenCalledTimes(1)
  })
})
