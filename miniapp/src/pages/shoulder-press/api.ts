import Taro from '@tarojs/taro'

import { request } from '../../api/client'

export type ShoulderPressUploadIntent = {
  video_id: number
  bucket: string
  key: string
  upload_token: string
  upload_host: string
  expires_at: string
}

type QiniuUploadErrorReason =
  | 'token_expired'
  | 'http'
  | 'invalid_response'
  | 'key_mismatch'
  | 'transport'

function qiniuErrorMessage(reason: QiniuUploadErrorReason, statusCode?: number): string {
  if (reason === 'token_expired') return '上传凭证已过期，正在重新申请'
  if (reason === 'http') return `视频上传失败（HTTP ${statusCode ?? '未知'}）`
  if (reason === 'invalid_response') return '视频上传响应格式无效'
  if (reason === 'key_mismatch') return '视频上传结果与申请凭证不一致'
  return '视频上传失败，请检查网络后重试'
}

export class QiniuUploadError extends Error {
  readonly reason: QiniuUploadErrorReason

  constructor(reason: QiniuUploadErrorReason, statusCode?: number) {
    super(qiniuErrorMessage(reason, statusCode))
    this.name = 'QiniuUploadError'
    this.reason = reason
  }
}

export function isQiniuTokenExpiredError(error: unknown): boolean {
  return error instanceof QiniuUploadError && error.reason === 'token_expired'
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

function responseReportsExpiredToken(data: string): boolean {
  const parsed = parseJsonObject(data)
  if (!parsed) return false
  const error = parsed.error
  return typeof error === 'string' && /token.*expired|expired.*token/i.test(error)
}

export async function createShoulderPressUploadIntent(input: {
  actionId: number
  sizeBytes: number
  durationSeconds: number
}): Promise<ShoulderPressUploadIntent> {
  return request<ShoulderPressUploadIntent>('/patient-app/training-videos/upload-intent/', {
    method: 'POST',
    data: {
      prescription_action: input.actionId,
      content_type: 'video/mp4',
      size_bytes: input.sizeBytes,
      duration_seconds: input.durationSeconds
    }
  })
}

export async function uploadVideoToQiniu(input: {
  uploadHost: string
  key: string
  uploadToken: string
  filePath: string
  onProgress?: (progress: number) => void
}): Promise<{ key: string; hash: string }> {
  return new Promise((resolve, reject) => {
    try {
      const task = Taro.uploadFile({
        url: input.uploadHost,
        filePath: input.filePath,
        name: 'file',
        formData: {
          key: input.key,
          token: input.uploadToken
        },
        success(response) {
          if (response.statusCode < 200 || response.statusCode >= 300) {
            if (responseReportsExpiredToken(response.data)) {
              reject(new QiniuUploadError('token_expired'))
              return
            }
            reject(new QiniuUploadError('http', response.statusCode))
            return
          }

          const data = parseJsonObject(response.data)
          if (!data || typeof data.key !== 'string' || typeof data.hash !== 'string' || !data.hash.trim()) {
            reject(new QiniuUploadError('invalid_response'))
            return
          }
          if (data.key !== input.key) {
            reject(new QiniuUploadError('key_mismatch'))
            return
          }
          resolve({ key: data.key, hash: data.hash })
        },
        fail() {
          reject(new QiniuUploadError('transport'))
        }
      })

      if (input.onProgress && task && typeof task.onProgressUpdate === 'function') {
        task.onProgressUpdate((event) => {
          if (!Number.isFinite(event.progress)) return
          input.onProgress?.(Math.max(0, Math.min(100, Math.round(event.progress))))
        })
      }
    } catch {
      reject(new QiniuUploadError('transport'))
    }
  })
}

export async function completeShoulderPressUpload(input: {
  videoId: number
  key: string
  hash: string
  trainingDate: string
  actualDurationMinutes: number
  note: string
}): Promise<unknown> {
  return request(`/patient-app/training-videos/${input.videoId}/complete/`, {
    method: 'POST',
    data: {
      key: input.key,
      hash: input.hash,
      training_date: input.trainingDate,
      actual_duration_minutes: input.actualDurationMinutes,
      note: input.note
    }
  })
}
