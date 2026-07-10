import Taro from '@tarojs/taro'

import {
  apiUrl,
  handlePatientUnauthorized,
  patientAuthorizationHeader,
  request,
  safeApiErrorMessage
} from '../../api/client'
import { createClientSessionId } from './session'

export type VideoSessionStatus = {
  video_id: number
  status: string
  uploaded_segments?: number[]
  assembly_job_id?: string
}

export type UploadedVideoSegment = {
  index: number
  sha256: string
}

type UploadFileSuccess = {
  statusCode: number
  data: string
}

function parseJsonObject(value: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(value) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    return parsed as Record<string, unknown>
  } catch {
    return null
  }
}

function uploadErrorMessage(data: string): string {
  const parsed = parseJsonObject(data)
  return safeApiErrorMessage(parsed ?? data)
}

function parseUploadedSegment(data: string, expectedIndex: number): UploadedVideoSegment {
  const parsed = parseJsonObject(data)
  if (!parsed || parsed.index !== expectedIndex || typeof parsed.sha256 !== 'string' || !parsed.sha256.trim()) {
    throw new Error('视频分段上传响应格式无效')
  }
  return { index: expectedIndex, sha256: parsed.sha256 }
}

export async function createVideoSession(input: {
  actionId: number
  clientSessionId: string
  trainingDate: string
  expectedDurationSeconds: number
}): Promise<VideoSessionStatus> {
  return request<VideoSessionStatus>('/patient-app/training-video-sessions/', {
    method: 'POST',
    data: {
      prescription_action: input.actionId,
      client_session_id: input.clientSessionId,
      training_date: input.trainingDate,
      expected_duration_seconds: input.expectedDurationSeconds
    }
  })
}

export async function uploadVideoSegment(input: {
  videoId: number
  index: number
  filePath: string
  durationMs: number
  sizeBytes: number
  onProgress?: (progress: number) => void
}): Promise<UploadedVideoSegment> {
  return new Promise((resolve, reject) => {
    try {
      const task = Taro.uploadFile({
        url: apiUrl(`/patient-app/training-video-sessions/${input.videoId}/segments/${input.index}/`),
        filePath: input.filePath,
        name: 'file',
        header: patientAuthorizationHeader(),
        formData: {
          duration_ms: input.durationMs,
          size_bytes: input.sizeBytes
        },
        success(response: UploadFileSuccess) {
          if (response.statusCode === 401 || response.statusCode === 403) {
            try {
              handlePatientUnauthorized()
            } catch (error) {
              reject(error)
            }
            return
          }
          if (response.statusCode < 200 || response.statusCode >= 300) {
            reject(new Error(uploadErrorMessage(response.data)))
            return
          }
          try {
            resolve(parseUploadedSegment(response.data, input.index))
          } catch (error) {
            reject(error)
          }
        },
        fail() {
          reject(new Error('视频分段上传失败，请检查网络后重试'))
        }
      })

      if (input.onProgress && task && typeof task.onProgressUpdate === 'function') {
        task.onProgressUpdate((event) => {
          if (!Number.isFinite(event.progress)) return
          input.onProgress?.(Math.max(0, Math.min(100, Math.round(event.progress))))
        })
      }
    } catch {
      reject(new Error('视频分段上传失败，请检查网络后重试'))
    }
  })
}

export async function finalizeVideoSession(input: {
  videoId: number
  segmentCount: number
  actualDurationSeconds: number
  note: string
}): Promise<VideoSessionStatus> {
  return request<VideoSessionStatus>(`/patient-app/training-video-sessions/${input.videoId}/finalize/`, {
    method: 'POST',
    data: {
      segment_count: input.segmentCount,
      actual_duration_seconds: input.actualDurationSeconds,
      note: input.note
    }
  })
}

export async function getVideoSessionStatus(videoId: number): Promise<VideoSessionStatus> {
  return request<VideoSessionStatus>(`/patient-app/training-video-sessions/${videoId}/status/`)
}

export async function createShoulderPressUploadIntent(input: {
  actionId: number
  durationSeconds: number
}): Promise<VideoSessionStatus> {
  return createVideoSession({
    actionId: input.actionId,
    clientSessionId: createClientSessionId(),
    trainingDate: new Date().toISOString().slice(0, 10),
    expectedDurationSeconds: input.durationSeconds
  })
}

export async function uploadVideoToQiniu(input: Record<string, unknown> & {
  filePath: string
  onProgress?: (progress: number) => void
}): Promise<{ key: string; hash: string }> {
  const uploaded = await uploadVideoSegment({
    videoId: 0,
    index: 0,
    filePath: input.filePath,
    durationMs: 1,
    sizeBytes: 1,
    onProgress: input.onProgress
  })
  return { key: String(uploaded.index), hash: uploaded.sha256 }
}

export async function completeShoulderPressUpload(input: {
  videoId: number
  actualDurationMinutes: number
  note: string
} & Record<string, unknown>): Promise<VideoSessionStatus> {
  return finalizeVideoSession({
    videoId: input.videoId,
    segmentCount: 1,
    actualDurationSeconds: input.actualDurationMinutes * 60,
    note: input.note
  })
}

export function isQiniuTokenExpiredError(): boolean {
  return false
}
