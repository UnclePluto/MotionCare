import Taro from '@tarojs/taro'

import {
  apiUrl,
  handlePatientUnauthorized,
  patientAuthorizationHeader,
  request,
  safeApiErrorMessage
} from '../../api/client'
import {
  createClientSessionId,
  normalizeShoulderPressExpectedDurationSeconds
} from './session'

const TRAINING_VIDEO_STATUSES = new Set([
  'recording',
  'uploading_segments',
  'queued',
  'assembling',
  'uploading_qiniu',
  'attached',
  'failed',
  'expired'
] as const)

type TrainingVideoStatus = typeof TRAINING_VIDEO_STATUSES extends Set<infer T> ? T : never

export type VideoSessionStatus = {
  video_id: number
  status: TrainingVideoStatus
  uploaded_segments?: number[]
  assembly_job_id?: number
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

function isObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function isPositiveInteger(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) > 0
}

function isTrainingVideoStatus(value: unknown): value is TrainingVideoStatus {
  return typeof value === 'string' && TRAINING_VIDEO_STATUSES.has(value as TrainingVideoStatus)
}

function parseUploadedSegments(value: unknown): number[] {
  if (!Array.isArray(value)) throw new Error('视频会话响应格式无效')
  if (!value.every((index) => Number.isInteger(index) && Number(index) >= 0)) {
    throw new Error('视频会话响应格式无效')
  }
  return value as number[]
}

type ParseVideoSessionStatusOptions = {
  requireUploadedSegments?: boolean
  requireAssemblyJobId?: boolean
  expectedVideoId?: number
}

function parseVideoSessionStatus(value: unknown, options: ParseVideoSessionStatusOptions = {}): VideoSessionStatus {
  if (!isObject(value) || !isPositiveInteger(value.video_id) || !isTrainingVideoStatus(value.status)) {
    throw new Error('视频会话响应格式无效')
  }

  if (options.expectedVideoId !== undefined && value.video_id !== options.expectedVideoId) {
    throw new Error('视频会话响应格式无效')
  }

  const parsed: VideoSessionStatus = {
    video_id: value.video_id,
    status: value.status
  }

  if (options.requireUploadedSegments || value.uploaded_segments !== undefined) {
    parsed.uploaded_segments = parseUploadedSegments(value.uploaded_segments)
  }

  if (options.requireAssemblyJobId || value.assembly_job_id !== undefined) {
    if (isPositiveInteger(value.assembly_job_id)) {
      parsed.assembly_job_id = value.assembly_job_id
    } else {
      throw new Error('视频会话响应格式无效')
    }
  }

  return parsed
}

export async function createVideoSession(input: {
  actionId: number
  clientSessionId: string
  trainingDate: string
  expectedDurationSeconds: number
  trainingStartedAt?: string
}): Promise<VideoSessionStatus> {
  const response = await request<unknown>('/patient-app/training-video-sessions/', {
    method: 'POST',
    data: {
      prescription_action: input.actionId,
      client_session_id: input.clientSessionId,
      training_date: input.trainingDate,
      expected_duration_seconds: normalizeShoulderPressExpectedDurationSeconds(
        input.expectedDurationSeconds
      ),
      ...(input.trainingStartedAt
        ? { training_started_at: input.trainingStartedAt }
        : {})
    }
  })
  return parseVideoSessionStatus(response, { requireUploadedSegments: true })
}

export async function uploadVideoSegment(input: {
  videoId: number
  index: number
  filePath: string
  durationMs: number
  sizeBytes: number
  onProgress?: (progress: number) => void
}): Promise<UploadedVideoSegment> {
  let exactSizeBytes: number
  try {
    const fileInfo = await Taro.getFileInfo({ filePath: input.filePath })
    if (!isObject(fileInfo) || !isPositiveInteger(fileInfo.size)) {
      throw new Error('invalid file info')
    }
    exactSizeBytes = fileInfo.size
  } catch {
    throw new Error('无法读取录像分段实际大小，请重试')
  }

  return new Promise((resolve, reject) => {
    let settled = false
    const settleResolve = (value: UploadedVideoSegment) => {
      if (settled) return
      settled = true
      resolve(value)
    }
    const settleReject = (error: Error) => {
      if (settled) return
      settled = true
      reject(error)
    }

    try {
      const task = Taro.uploadFile({
        url: apiUrl(`/patient-app/training-video-sessions/${input.videoId}/segments/${input.index}/`),
        filePath: input.filePath,
        name: 'file',
        header: patientAuthorizationHeader(),
        formData: {
          duration_ms: input.durationMs,
          size_bytes: exactSizeBytes
        },
        success(response: UploadFileSuccess) {
          if (settled) return
          if (response.statusCode === 401 || response.statusCode === 403) {
            try {
              handlePatientUnauthorized()
            } catch (error) {
              settleReject(error instanceof Error ? error : new Error('登录已失效'))
            }
            return
          }
          if (response.statusCode < 200 || response.statusCode >= 300) {
            settleReject(new Error(uploadErrorMessage(response.data)))
            return
          }
          try {
            settleResolve(parseUploadedSegment(response.data, input.index))
          } catch (error) {
            settleReject(error instanceof Error ? error : new Error('视频分段上传响应格式无效'))
          }
        },
        fail() {
          settleReject(new Error('视频分段上传失败，请检查网络后重试'))
        }
      })

      if (input.onProgress && task && typeof task.onProgressUpdate === 'function') {
        task.onProgressUpdate((event) => {
          if (!Number.isFinite(event.progress)) return
          input.onProgress?.(Math.max(0, Math.min(100, Math.round(event.progress))))
        })
      }
    } catch {
      settleReject(new Error('视频分段上传失败，请检查网络后重试'))
    }
  })
}

export async function finalizeVideoSession(input: {
  videoId: number
  segmentCount: number
  actualDurationSeconds: number
  note: string
  trainingEndedAt?: string
}): Promise<VideoSessionStatus> {
  const response = await request<unknown>(`/patient-app/training-video-sessions/${input.videoId}/finalize/`, {
    method: 'POST',
    data: {
      segment_count: input.segmentCount,
      actual_duration_seconds: input.actualDurationSeconds,
      note: input.note,
      ...(input.trainingEndedAt
        ? { training_ended_at: input.trainingEndedAt }
        : {})
    }
  })
  return parseVideoSessionStatus(response, {
    requireAssemblyJobId: true,
    expectedVideoId: input.videoId
  })
}

export async function getVideoSessionStatus(videoId: number): Promise<VideoSessionStatus> {
  const response = await request<unknown>(`/patient-app/training-video-sessions/${videoId}/status/`)
  return parseVideoSessionStatus(response, {
    requireUploadedSegments: true,
    expectedVideoId: videoId
  })
}

export async function createShoulderPressUploadIntent(input: {
  actionId: number
  durationSeconds: number
  clientSessionId?: string
  trainingDate?: string
  expectedDurationSeconds?: number
  trainingStartedAt?: string
}): Promise<VideoSessionStatus> {
  return createVideoSession({
    actionId: input.actionId,
    clientSessionId: input.clientSessionId ?? createClientSessionId(),
    trainingDate: input.trainingDate ?? new Date().toISOString().slice(0, 10),
    expectedDurationSeconds: input.expectedDurationSeconds ?? input.durationSeconds,
    trainingStartedAt: input.trainingStartedAt
  })
}

export async function uploadVideoToQiniu(input: Record<string, unknown> & {
  filePath: string
  onProgress?: (progress: number) => void
}): Promise<{ key: string; hash: string }> {
  if (
    !Number.isInteger(input.videoId) ||
    Number(input.videoId) <= 0 ||
    !Number.isInteger(input.index) ||
    Number(input.index) < 0 ||
    !Number.isInteger(input.durationMs) ||
    Number(input.durationMs) <= 0 ||
    !Number.isInteger(input.sizeBytes) ||
    Number(input.sizeBytes) <= 0
  ) {
    throw new Error('录像上传信息不完整，请重新开始')
  }

  const uploaded = await uploadVideoSegment({
    videoId: Number(input.videoId),
    index: Number(input.index),
    filePath: input.filePath,
    durationMs: Number(input.durationMs),
    sizeBytes: Number(input.sizeBytes),
    onProgress: input.onProgress
  })
  return { key: String(uploaded.index), hash: uploaded.sha256 }
}

export async function completeShoulderPressUpload(input: {
  videoId: number
  actualDurationMinutes: number
  note: string
  trainingEndedAt?: string
} & Record<string, unknown>): Promise<VideoSessionStatus> {
  return finalizeVideoSession({
    videoId: input.videoId,
    segmentCount: 1,
    actualDurationSeconds: input.actualDurationMinutes * 60,
    note: input.note,
    trainingEndedAt: input.trainingEndedAt
  })
}

export function isQiniuTokenExpiredError(): boolean {
  return false
}
