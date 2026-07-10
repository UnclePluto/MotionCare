import { describe, expect, it, vi } from 'vitest'
import {
  completeShoulderPressUpload,
  createShoulderPressUploadIntent,
  isQiniuTokenExpiredError,
  uploadVideoToQiniu
} from './api'

const { mockRequest, mockUploadFile } = vi.hoisted(() => ({
  mockRequest: vi.fn(),
  mockUploadFile: vi.fn()
}))

vi.mock('../../api/client', () => ({
  request: (...args: unknown[]) => mockRequest(...args)
}))

vi.mock('@tarojs/taro', () => ({
  default: {
    uploadFile: (...args: unknown[]) => mockUploadFile(...args)
  }
}))

describe('shoulder press upload api', () => {
  it('creates an upload intent through the patient app api', async () => {
    mockRequest.mockResolvedValue({
      video_id: 1,
      bucket: 'motioncare-training',
      key: 'k',
      upload_token: 'token',
      upload_host: 'https://upload.qiniup.com',
      expires_at: '2026-07-10T19:00:00+08:00'
    })

    await createShoulderPressUploadIntent({ actionId: 42, sizeBytes: 100, durationSeconds: 30 })

    expect(mockRequest).toHaveBeenCalledWith('/patient-app/training-videos/upload-intent/', {
      method: 'POST',
      data: {
        prescription_action: 42,
        content_type: 'video/mp4',
        size_bytes: 100,
        duration_seconds: 30
      }
    })
  })

  it('uploads to qiniu and reports normalized progress', async () => {
    const progress: number[] = []
    mockUploadFile.mockImplementation((options) => {
      const task = {
        onProgressUpdate(callback) {
          callback({ progress: 36.6, totalBytesSent: 366, totalBytesExpectedToSend: 1000 })
        }
      }
      queueMicrotask(() => options.success({ statusCode: 200, data: '{"key":"k","hash":"h"}' }))
      return task
    })

    await expect(uploadVideoToQiniu({
      uploadHost: 'https://upload.qiniup.com',
      key: 'k',
      uploadToken: 'token',
      filePath: 'wxfile://video.mp4',
      onProgress: (value) => progress.push(value)
    })).resolves.toEqual({ key: 'k', hash: 'h' })
    expect(progress).toEqual([37])
  })

  it('rejects non-2xx, malformed json, and a mismatched response key', async () => {
    mockUploadFile
      .mockImplementationOnce((options) => {
        queueMicrotask(() => options.success({ statusCode: 500, data: '{"error":"server error"}' }))
        return { onProgressUpdate: vi.fn() }
      })
      .mockImplementationOnce((options) => {
        queueMicrotask(() => options.success({ statusCode: 200, data: 'not-json' }))
        return { onProgressUpdate: vi.fn() }
      })
      .mockImplementationOnce((options) => {
        queueMicrotask(() => options.success({ statusCode: 200, data: '{"key":"other","hash":"h"}' }))
        return { onProgressUpdate: vi.fn() }
      })

    const input = {
      uploadHost: 'https://upload.qiniup.com',
      key: 'expected',
      uploadToken: 'secret-token',
      filePath: 'wxfile://video.mp4'
    }
    await expect(uploadVideoToQiniu(input)).rejects.toThrow('视频上传失败（HTTP 500）')
    await expect(uploadVideoToQiniu(input)).rejects.toThrow('视频上传响应格式无效')
    await expect(uploadVideoToQiniu(input)).rejects.toThrow('视频上传结果与申请凭证不一致')
  })

  it('classifies an explicit qiniu token expiry without exposing the token', async () => {
    mockUploadFile.mockImplementation((options) => {
      queueMicrotask(() => options.success({ statusCode: 401, data: '{"error":"token has expired: secret-token"}' }))
      return { onProgressUpdate: vi.fn() }
    })

    const promise = uploadVideoToQiniu({
      uploadHost: 'https://upload.qiniup.com',
      key: 'k',
      uploadToken: 'secret-token',
      filePath: 'wxfile://video.mp4'
    })

    await expect(promise).rejects.toSatisfy((error: unknown) => isQiniuTokenExpiredError(error))
    await expect(promise).rejects.not.toThrow(/secret-token/)
  })

  it('does not expose transport error details that may contain credentials', async () => {
    mockUploadFile.mockImplementation((options) => {
      queueMicrotask(() => options.fail({ errMsg: 'upload failed with secret-token' }))
      return { onProgressUpdate: vi.fn() }
    })

    await expect(uploadVideoToQiniu({
      uploadHost: 'https://upload.qiniup.com',
      key: 'k',
      uploadToken: 'secret-token',
      filePath: 'wxfile://video.mp4'
    })).rejects.toThrow('视频上传失败，请检查网络后重试')
  })

  it('completes upload with the original training fields', async () => {
    mockRequest.mockResolvedValue({ video_id: 1, status: 'attached' })

    await completeShoulderPressUpload({
      videoId: 1,
      key: 'k',
      hash: 'h',
      trainingDate: '2026-07-10',
      actualDurationMinutes: 2,
      note: ''
    })

    expect(mockRequest).toHaveBeenCalledWith('/patient-app/training-videos/1/complete/', {
      method: 'POST',
      data: {
        key: 'k',
        hash: 'h',
        training_date: '2026-07-10',
        actual_duration_minutes: 2,
        note: ''
      }
    })
  })
})
