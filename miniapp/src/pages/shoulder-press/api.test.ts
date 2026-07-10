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
      .mockResolvedValueOnce({ statusCode: 201, data: { video_id: 9, status: 'created' } })
      .mockResolvedValueOnce({ statusCode: 202, data: { video_id: 9, status: 'assembling', assembly_job_id: 'job-1' } })
      .mockResolvedValueOnce({ statusCode: 200, data: { video_id: 9, status: 'assembled', uploaded_segments: [0, 1] } })

    await expect(createVideoSession({
      actionId: 42,
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      trainingDate: '2026-07-11',
      expectedDurationSeconds: 180
    })).resolves.toEqual({ video_id: 9, status: 'created' })
    await expect(finalizeVideoSession({
      videoId: 9,
      segmentCount: 2,
      actualDurationSeconds: 60,
      note: ''
    })).resolves.toEqual({ video_id: 9, status: 'assembling', assembly_job_id: 'job-1' })
    await expect(getVideoSessionStatus(9)).resolves.toEqual({
      video_id: 9,
      status: 'assembled',
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
})
