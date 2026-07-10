import { todayLocalDate } from '../../utils/date'
import {
  isQiniuTokenExpiredError,
  type ShoulderPressUploadIntent
} from './api'
import {
  clearShoulderPressUploadIntent,
  hasShoulderPressUploadIntent,
  type PendingShoulderPressUpload
} from './session'

export type ShoulderPressUploadPhase = 'credential' | 'upload' | 'complete'

export type ShoulderPressUploadEvent = {
  phase: ShoulderPressUploadPhase
  progress: number
}

type UploadInput = {
  uploadHost: string
  key: string
  uploadToken: string
  filePath: string
  onProgress?: (progress: number) => void
}

type CompleteInput = {
  videoId: number
  key: string
  hash: string
  trainingDate: string
  actualDurationMinutes: number
  note: string
}

export type ShoulderPressUploadWorkflowDependencies = {
  now: () => number
  createIntent: (input: {
    actionId: number
    sizeBytes: number
    durationSeconds: number
  }) => Promise<ShoulderPressUploadIntent>
  uploadVideo: (input: UploadInput) => Promise<{ key: string; hash: string }>
  completeUpload: (input: CompleteInput) => Promise<unknown>
  savePending: (pending: PendingShoulderPressUpload) => void
}

export function shoulderPressUploadErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) return '上传失败，请检查网络后重试'
  const message = error.message.trim()
  if (!message || /token|secret/i.test(message) || !/[\u3400-\u9fff]/.test(message)) {
    return '上传失败，请检查网络后重试'
  }
  return message
}

function expiryTimestamp(value: string): number {
  const timestamp = Date.parse(value)
  if (!Number.isFinite(timestamp)) throw new Error('上传凭证有效期无效，请重试')
  return timestamp
}

function durationMinutes(seconds: number): number {
  return Math.max(1, Math.ceil(seconds / 60))
}

function persistFailure(
  pending: PendingShoulderPressUpload,
  error: unknown,
  savePending: ShoulderPressUploadWorkflowDependencies['savePending']
): void {
  savePending({ ...pending, lastError: shoulderPressUploadErrorMessage(error) })
}

export async function runShoulderPressUploadWorkflow(
  initialPending: PendingShoulderPressUpload,
  dependencies: ShoulderPressUploadWorkflowDependencies,
  onEvent: (event: ShoulderPressUploadEvent) => void
): Promise<PendingShoulderPressUpload> {
  let pending: PendingShoulderPressUpload = { ...initialPending, lastError: undefined }
  let expiryReplacementCount = 0

  while (!pending.hash) {
    if (hasShoulderPressUploadIntent(pending) && pending.expiresAt <= dependencies.now()) {
      pending = clearShoulderPressUploadIntent(pending)
      dependencies.savePending(pending)
    }

    if (!hasShoulderPressUploadIntent(pending)) {
      onEvent({ phase: 'credential', progress: 0 })
      let intent: ShoulderPressUploadIntent
      try {
        intent = await dependencies.createIntent({
          actionId: pending.actionId,
          sizeBytes: pending.sizeBytes,
          durationSeconds: pending.durationSeconds
        })
        const expiresAt = expiryTimestamp(intent.expires_at)
        if (expiresAt <= dependencies.now()) {
          throw new Error('上传凭证已过期，请重试')
        }
        const nextPending: PendingShoulderPressUpload = {
          ...pending,
          videoId: intent.video_id,
          key: intent.key,
          uploadToken: intent.upload_token,
          uploadHost: intent.upload_host,
          expiresAt,
          lastError: undefined
        }
        if (!hasShoulderPressUploadIntent(nextPending)) {
          throw new Error('上传凭证信息不完整，请重试')
        }
        pending = nextPending
        dependencies.savePending(pending)
        onEvent({ phase: 'credential', progress: 100 })
      } catch (error) {
        persistFailure(pending, error, dependencies.savePending)
        throw error
      }
    }

    if (!hasShoulderPressUploadIntent(pending)) {
      throw new Error('上传凭证信息不完整，请重试')
    }

    onEvent({ phase: 'upload', progress: 0 })
    try {
      const uploaded = await dependencies.uploadVideo({
        uploadHost: pending.uploadHost,
        key: pending.key,
        uploadToken: pending.uploadToken,
        filePath: pending.tempFilePath,
        onProgress: (progress) => onEvent({ phase: 'upload', progress })
      })
      pending = { ...pending, hash: uploaded.hash, lastError: undefined }
      dependencies.savePending(pending)
      onEvent({ phase: 'upload', progress: 100 })
    } catch (error) {
      if (isQiniuTokenExpiredError(error)) {
        pending = clearShoulderPressUploadIntent(pending)
        dependencies.savePending(pending)
        if (expiryReplacementCount === 0) {
          expiryReplacementCount += 1
          continue
        }
      }
      persistFailure(pending, error, dependencies.savePending)
      throw error
    }
  }

  if (!hasShoulderPressUploadIntent(pending)) {
    throw new Error('已上传视频信息不完整，请重新开始')
  }

  onEvent({ phase: 'complete', progress: 0 })
  try {
    await dependencies.completeUpload({
      videoId: pending.videoId,
      key: pending.key,
      hash: pending.hash,
      trainingDate: todayLocalDate(),
      actualDurationMinutes: durationMinutes(pending.durationSeconds),
      note: ''
    })
    onEvent({ phase: 'complete', progress: 100 })
    return pending
  } catch (error) {
    persistFailure(pending, error, dependencies.savePending)
    throw error
  }
}
