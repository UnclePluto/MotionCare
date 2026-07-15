import Taro from '@tarojs/taro'

import { apiUrl, request } from '../../api/client'
import { getPatientAppToken } from '../../auth/token'

export type ShoulderPressVideoSessionStatus = {
  video_id: number
  status: string
  uploaded_segment_count: number
  segment_count: number
  duration_seconds: number
  processing: null | {
    status: string
    progress_percent: number
  }
  training_record_id: number | null
}

export function createShoulderPressVideoSession(actionId: number): Promise<{
  video_id: number
  status: string
  uploaded_segment_count: number
}> {
  return request('/patient-app/training-video-sessions/', {
    method: 'POST',
    data: { prescription_action: actionId },
  })
}

export function uploadShoulderPressSegment(input: {
  videoId: number
  sequenceIndex: number
  durationSeconds: number
  filePath: string
  onProgress?: (progress: number) => void
}): Promise<{ sequence_index: number; object_hash: string }> {
  return new Promise((resolve, reject) => {
    const token = getPatientAppToken()
    const task = Taro.uploadFile({
      url: apiUrl(`/patient-app/training-video-sessions/${input.videoId}/segments/`),
      filePath: input.filePath,
      name: 'file',
      formData: {
        sequence_index: String(input.sequenceIndex),
        duration_seconds: String(input.durationSeconds),
      },
      header: token ? { Authorization: `Bearer ${token}` } : {},
      success(response) {
        try {
          const data = JSON.parse(response.data || '{}') as {
            detail?: string
            sequence_index?: number
            object_hash?: string
          }
          if (response.statusCode < 200 || response.statusCode >= 300) {
            reject(new Error(data.detail || `视频分片上传失败（${response.statusCode}）`))
            return
          }
          if (typeof data.sequence_index !== 'number' || !data.object_hash) {
            throw new Error('分片上传响应不完整')
          }
          resolve({ sequence_index: data.sequence_index, object_hash: data.object_hash })
        } catch (error) {
          reject(error instanceof Error ? error : new Error('分片上传响应解析失败'))
        }
      },
      fail(error) {
        reject(new Error(error.errMsg || '视频分片上传失败'))
      },
    })
    task.onProgressUpdate?.((event) => input.onProgress?.(event.progress))
  })
}

export function finishShoulderPressVideoSession(input: {
  videoId: number
  segmentCount: number
  durationSeconds: number
  trainingDate: string
}) {
  return request(`/patient-app/training-video-sessions/${input.videoId}/finish/`, {
    method: 'POST',
    data: {
      segment_count: input.segmentCount,
      duration_seconds: input.durationSeconds,
      training_date: input.trainingDate,
    },
  })
}

export function getShoulderPressVideoSession(
  videoId: number,
): Promise<ShoulderPressVideoSessionStatus> {
  return request(`/patient-app/training-video-sessions/${videoId}/`)
}
