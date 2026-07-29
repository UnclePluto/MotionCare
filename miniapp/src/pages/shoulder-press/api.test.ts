import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockRequest, mockUploadFile } = vi.hoisted(() => ({
  mockRequest: vi.fn(),
  mockUploadFile: vi.fn(),
}))

vi.mock('../../api/client', () => ({
  apiUrl: (path: string) => `http://127.0.0.1:8000/api${path}`,
  request: (...args: unknown[]) => mockRequest(...args),
}))
vi.mock('../../auth/token', () => ({ getPatientAppToken: () => 'patient-token' }))
vi.mock('@tarojs/taro', () => ({
  default: { uploadFile: (...args: unknown[]) => mockUploadFile(...args) },
}))

import {
  createShoulderPressVideoSession,
  finishShoulderPressVideoSession,
  getShoulderPressVideoSession,
  uploadShoulderPressSegment,
} from './api'

describe('肩部推举分片 API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('只用处方动作创建服务端录像会话', async () => {
    mockRequest.mockResolvedValue({ video_id: 1, status: 'recording' })

    await createShoulderPressVideoSession(42)

    expect(mockRequest).toHaveBeenCalledWith(
      '/patient-app/training-video-sessions/',
      { method: 'POST', data: { prescription_action: 42 } },
    )
  })

  it('分片固定上传业务服务器且携带患者 token', async () => {
    const onProgress = vi.fn()
    mockUploadFile.mockImplementation((options) => {
      options.success({
        statusCode: 201,
        data: '{"sequence_index":0,"object_hash":"segment-hash"}',
      })
      return {
        onProgressUpdate(callback) {
          callback({
            progress: 25,
            totalBytesSent: 250,
            totalBytesExpectedToSend: 1_000,
          })
        },
      }
    })

    await expect(uploadShoulderPressSegment({
      videoId: 7,
      sequenceIndex: 0,
      durationSeconds: 30,
      filePath: 'wxfile://segment-0.mp4',
      onProgress,
    })).resolves.toEqual({ sequence_index: 0, object_hash: 'segment-hash' })

    expect(mockUploadFile).toHaveBeenCalledWith(expect.objectContaining({
      url: 'http://127.0.0.1:8000/api/patient-app/training-video-sessions/7/segments/',
      header: { Authorization: 'Bearer patient-token' },
      formData: { sequence_index: '0', duration_seconds: '30' },
    }))
    expect(onProgress).toHaveBeenCalledWith({
      progress: 25,
      totalBytesSent: 250,
      totalBytesExpectedToSend: 1_000,
    })
  })

  it('结束会话后只轮询服务端处理状态', async () => {
    mockRequest.mockResolvedValue({ status: 'queued' })

    await finishShoulderPressVideoSession({
      videoId: 7,
      segmentCount: 3,
      durationSeconds: 70,
      trainingDate: '2026-07-14',
    })
    await getShoulderPressVideoSession(7)

    expect(mockRequest).toHaveBeenNthCalledWith(
      1,
      '/patient-app/training-video-sessions/7/finish/',
      {
        method: 'POST',
        data: {
          segment_count: 3,
          duration_seconds: 70,
          training_date: '2026-07-14',
        },
      },
    )
    expect(mockRequest).toHaveBeenNthCalledWith(
      2,
      '/patient-app/training-video-sessions/7/',
    )
  })
})
