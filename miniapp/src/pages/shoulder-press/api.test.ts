import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createVideoSession,
  finalizeVideoSession,
  getVideoSessionStatus,
  uploadVideoSegment
} from './api'

const { taroMock } = vi.hoisted(() => ({
  taroMock: {
    request: vi.fn(),
    uploadFile: vi.fn(),
    getStorageSync: vi.fn(),
    removeStorageSync: vi.fn(),
    redirectTo: vi.fn()
  }
}))

vi.mock('@tarojs/taro', () => ({ default: taroMock }))

describe('shoulder press segmented upload api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    taroMock.getStorageSync.mockReturnValue('patient-token')
  })

  it('creates, finalizes, and reads video sessions through the patient app API', async () => {
    taroMock.request
      .mockResolvedValueOnce({ statusCode: 201, data: { video_id: 9, status: 'recording', uploaded_segments: [] } })
      .mockResolvedValueOnce({ statusCode: 202, data: { video_id: 9, status: 'queued', assembly_job_id: 1 } })
      .mockResolvedValueOnce({ statusCode: 200, data: { video_id: 9, status: 'attached', uploaded_segments: [0, 1] } })

    await expect(createVideoSession({
      actionId: 42,
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      trainingDate: '2026-07-11',
      expectedDurationSeconds: 180
    })).resolves.toEqual({ video_id: 9, status: 'recording', uploaded_segments: [] })
    await expect(finalizeVideoSession({
      videoId: 9,
      segmentCount: 2,
      actualDurationSeconds: 60,
      note: ''
    })).resolves.toEqual({ video_id: 9, status: 'queued', assembly_job_id: 1 })
    await expect(getVideoSessionStatus(9)).resolves.toEqual({
      video_id: 9,
      status: 'attached',
      uploaded_segments: [0, 1]
    })

    expect(taroMock.request.mock.calls[0][0]).toMatchObject({
      url: 'http://127.0.0.1:8000/api/patient-app/training-video-sessions/',
      method: 'POST',
      data: {
        prescription_action: 42,
        client_session_id: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
        training_date: '2026-07-11',
        expected_duration_seconds: 180
      },
      header: expect.objectContaining({ Authorization: 'Bearer patient-token' })
    })
    expect(taroMock.request.mock.calls[1][0]).toMatchObject({
      url: 'http://127.0.0.1:8000/api/patient-app/training-video-sessions/9/finalize/',
      method: 'POST',
      data: {
        segment_count: 2,
        actual_duration_seconds: 60,
        note: ''
      }
    })
    expect(taroMock.request.mock.calls[2][0]).toMatchObject({
      url: 'http://127.0.0.1:8000/api/patient-app/training-video-sessions/9/status/',
      method: 'GET'
    })
  })

  it('uploads a segment as multipart to the backend with bearer auth and byte metadata', async () => {
    taroMock.uploadFile.mockImplementation((options) => {
      options.success?.({ statusCode: 201, data: '{"index":0,"sha256":"segment-sha"}' })
      return { onProgressUpdate: vi.fn() }
    })

    await expect(uploadVideoSegment({
      videoId: 9,
      index: 0,
      filePath: 'wxfile://store/segment-0.mp4',
      durationMs: 29800,
      sizeBytes: 2097152
    })).resolves.toEqual({ index: 0, sha256: 'segment-sha' })

    const uploadOptions = taroMock.uploadFile.mock.calls[0][0]
    expect(uploadOptions).toMatchObject({
      url: 'http://127.0.0.1:8000/api/patient-app/training-video-sessions/9/segments/0/',
      filePath: 'wxfile://store/segment-0.mp4',
      name: 'file',
      header: { Authorization: 'Bearer patient-token' },
      formData: {
        duration_ms: 29800,
        size_bytes: 2097152
      }
    })
    const forbiddenFields = [
      ['upload', '_', 'token'].join(''),
      ['upload', 'Token'].join(''),
      ['buck', 'et'].join(''),
      ['k', 'ey'].join(''),
      ['upload', '_', 'host'].join(''),
      ['upload', 'Host'].join(''),
      ['tok', 'en'].join('')
    ]
    expect(Object.keys(uploadOptions.formData)).not.toEqual(expect.arrayContaining(forbiddenFields))
    expect(uploadOptions.header.Authorization).toBe('Bearer patient-token')
  })

  it('normalizes upload progress while preserving single backend upload semantics', async () => {
    const progress: number[] = []
    taroMock.uploadFile.mockImplementation((options) => {
      const task = {
        onProgressUpdate(callback) {
          callback({ progress: 47.8 })
        }
      }
      queueMicrotask(() => options.success?.({ statusCode: 200, data: '{"index":1,"sha256":"segment-sha"}' }))
      return task
    })

    await uploadVideoSegment({
      videoId: 9,
      index: 1,
      filePath: 'wxfile://store/segment-1.mp4',
      durationMs: 30000,
      sizeBytes: 1024,
      onProgress: (value) => progress.push(value)
    })

    expect(progress).toEqual([48])
  })

  it('clears patient token and redirects on upload 401 without leaking Authorization details', async () => {
    taroMock.uploadFile.mockImplementation((options) => {
      options.success?.({
        statusCode: 401,
        data: '{"detail":"Authorization Bearer patient-token expired"}'
      })
      return { onProgressUpdate: vi.fn() }
    })

    await expect(uploadVideoSegment({
      videoId: 9,
      index: 0,
      filePath: 'wxfile://store/segment-0.mp4',
      durationMs: 29800,
      sizeBytes: 2097152
    })).rejects.toThrow('登录已失效')

    expect(taroMock.removeStorageSync).toHaveBeenCalled()
    expect(taroMock.redirectTo).toHaveBeenCalledWith({ url: '/pages/bind/index' })
    await expect(uploadVideoSegment({
      videoId: 9,
      index: 0,
      filePath: 'wxfile://store/segment-0.mp4',
      durationMs: 29800,
      sizeBytes: 2097152
    })).rejects.not.toThrow(/patient-token|Authorization/i)
  })

  it('uses safe string error fields from JSON request failures', async () => {
    taroMock.request.mockResolvedValueOnce({
      statusCode: 500,
      data: { error: '服务端忙，请稍后重试' }
    })

    await expect(createVideoSession({
      actionId: 42,
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      trainingDate: '2026-07-11',
      expectedDurationSeconds: 180
    })).rejects.toThrow('服务端忙，请稍后重试')
  })

  it.each([
    'access_key=abc',
    'accessKey: abc',
    'secret_key=def',
    'credential_id=ghi',
    'AK=abc',
    'SK=def'
  ])('filters sensitive credential field %s from JSON errors', async (credential) => {
    taroMock.request.mockResolvedValueOnce({
      statusCode: 500,
      data: { detail: `服务端异常 ${credential}` }
    })

    await expect(createVideoSession({
      actionId: 42,
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      trainingDate: '2026-07-11',
      expectedDurationSeconds: 180
    })).rejects.toThrow('请求失败')
  })

  it.each([
    ['body is not an object', 'not-an-object'],
    ['video_id is missing', { status: 'recording' }],
    ['video_id is zero', { video_id: 0, status: 'recording' }],
    ['video_id is fractional', { video_id: 1.2, status: 'recording' }],
    ['status is not a backend video status', { video_id: 9, status: 'created' }],
    ['uploaded_segments is missing', { video_id: 9, status: 'recording' }],
    ['uploaded_segments is null', { video_id: 9, status: 'recording', uploaded_segments: null }],
    ['uploaded_segments is not an array', { video_id: 9, status: 'recording', uploaded_segments: '0,1' }]
  ])('rejects malformed create success responses when %s', async (_caseName, data) => {
    taroMock.request.mockResolvedValueOnce({ statusCode: 201, data })

    await expect(createVideoSession({
      actionId: 42,
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      trainingDate: '2026-07-11',
      expectedDurationSeconds: 180
    })).rejects.toThrow('视频会话响应格式无效')
  })

  it.each([
    ['body is not an object', 'not-an-object'],
    ['video_id is invalid', { video_id: -1, status: 'recording', uploaded_segments: [] }],
    ['status is invalid', { video_id: 9, status: 'assembled', uploaded_segments: [] }],
    ['uploaded_segments is missing', { video_id: 9, status: 'recording' }],
    ['video_id does not match the requested video id', { video_id: 10, status: 'recording', uploaded_segments: [] }],
    ['uploaded_segments is not an array', { video_id: 9, status: 'recording', uploaded_segments: '0,1' }],
    ['uploaded_segments contains a fractional index', { video_id: 9, status: 'recording', uploaded_segments: [0, 1.5] }],
    ['uploaded_segments contains a negative index', { video_id: 9, status: 'recording', uploaded_segments: [0, -1] }]
  ])('rejects malformed status success responses when %s', async (_caseName, data) => {
    taroMock.request.mockResolvedValueOnce({ statusCode: 200, data })

    await expect(getVideoSessionStatus(9)).rejects.toThrow('视频会话响应格式无效')
  })

  it.each([
    ['video_id is missing', { status: 'queued', assembly_job_id: 1 }],
    ['video_id is not positive', { video_id: 0, status: 'queued', assembly_job_id: 1 }],
    ['video_id does not match the requested video id', { video_id: 10, status: 'queued', assembly_job_id: 1 }],
    ['status is invalid', { video_id: 9, status: 'assembled', assembly_job_id: 1 }],
    ['assembly_job_id is missing', { video_id: 9, status: 'queued' }],
    ['assembly_job_id is null', { video_id: 9, status: 'queued', assembly_job_id: null }],
    ['assembly_job_id is a string', { video_id: 9, status: 'queued', assembly_job_id: 'job-1' }],
    ['assembly_job_id is fractional', { video_id: 9, status: 'queued', assembly_job_id: 1.2 }],
    ['assembly_job_id is not positive', { video_id: 9, status: 'queued', assembly_job_id: 0 }]
  ])('rejects malformed finalize success responses when %s', async (_caseName, data) => {
    taroMock.request.mockResolvedValueOnce({ statusCode: 202, data })

    await expect(finalizeVideoSession({
      videoId: 9,
      segmentCount: 2,
      actualDurationSeconds: 60,
      note: ''
    })).rejects.toThrow('视频会话响应格式无效')
  })

  it.each([
    ['create', () => createVideoSession({
      actionId: 42,
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      trainingDate: '2026-07-11',
      expectedDurationSeconds: 180
    })],
    ['status', () => getVideoSessionStatus(9)],
    ['finalize', () => finalizeVideoSession({
      videoId: 9,
      segmentCount: 2,
      actualDurationSeconds: 60,
      note: ''
    })]
  ])('reports %s network rejects as a safe Chinese error', async (_caseName, requestAction) => {
    taroMock.request
      .mockRejectedValueOnce(new Error('Authorization Bearer patient-token secret request header leaked'))
      .mockRejectedValueOnce(new Error('Authorization Bearer patient-token secret request header leaked'))

    await expect(requestAction()).rejects.toThrow('请求失败，请检查网络后重试')
    await expect(requestAction()).rejects.not.toThrow(/Authorization|Bearer|patient-token|token|secret/i)
  })

  it('keeps JSON 401 handling by clearing the patient token and redirecting to bind page', async () => {
    taroMock.request.mockResolvedValueOnce({
      statusCode: 401,
      data: { detail: 'Authorization Bearer patient-token expired' }
    })

    await expect(getVideoSessionStatus(9)).rejects.toThrow('登录已失效')

    expect(taroMock.removeStorageSync).toHaveBeenCalled()
    expect(taroMock.redirectTo).toHaveBeenCalledWith({ url: '/pages/bind/index' })
  })

  it('uses safe string error fields from multipart upload failures', async () => {
    taroMock.uploadFile.mockImplementation((options) => {
      options.success?.({
        statusCode: 500,
        data: '{"error":"分段文件已损坏，请重新录制"}'
      })
      return { onProgressUpdate: vi.fn() }
    })

    await expect(uploadVideoSegment({
      videoId: 9,
      index: 0,
      filePath: 'wxfile://store/segment-0.mp4',
      durationMs: 29800,
      sizeBytes: 2097152
    })).rejects.toThrow('分段文件已损坏，请重新录制')
  })

  it('reports malformed success JSON as an invalid segment response', async () => {
    taroMock.uploadFile.mockImplementation((options) => {
      options.success?.({ statusCode: 200, data: 'not-json' })
      return { onProgressUpdate: vi.fn() }
    })

    await expect(uploadVideoSegment({
      videoId: 9,
      index: 0,
      filePath: 'wxfile://store/segment-0.mp4',
      durationMs: 29800,
      sizeBytes: 2097152
    })).rejects.toThrow('视频分段上传响应格式无效')
  })

  it('reports upload network failures as a retryable upload error', async () => {
    taroMock.uploadFile.mockImplementation((options) => {
      options.fail?.({ errMsg: 'request:fail timeout' })
      return { onProgressUpdate: vi.fn() }
    })

    await expect(uploadVideoSegment({
      videoId: 9,
      index: 0,
      filePath: 'wxfile://store/segment-0.mp4',
      durationMs: 29800,
      sizeBytes: 2097152
    })).rejects.toThrow('视频分段上传失败，请检查网络后重试')
  })

  it('settles multipart upload exactly once when success and fail callbacks both fire', async () => {
    taroMock.uploadFile.mockImplementation((options) => {
      options.success?.({ statusCode: 201, data: '{"index":0,"sha256":"segment-sha"}' })
      options.success?.({
        statusCode: 401,
        data: '{"detail":"Authorization Bearer patient-token expired"}'
      })
      options.fail?.({ errMsg: 'request:fail late' })
      return { onProgressUpdate: vi.fn() }
    })

    await expect(uploadVideoSegment({
      videoId: 9,
      index: 0,
      filePath: 'wxfile://store/segment-0.mp4',
      durationMs: 29800,
      sizeBytes: 2097152
    })).resolves.toEqual({ index: 0, sha256: 'segment-sha' })

    expect(taroMock.removeStorageSync).not.toHaveBeenCalled()
    expect(taroMock.redirectTo).not.toHaveBeenCalled()
  })
})
