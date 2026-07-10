import type { UploadedVideoSegment, VideoSessionStatus } from './api'
import {
  isSegmentReadyForLocalDeletion,
  markServerUploadedSegments,
  type PendingShoulderPressSegment,
  type PendingShoulderPressSession,
  type PendingShoulderPressUpload
} from './session'

export type ShoulderPressUploadPhase = 'session' | 'status' | 'upload' | 'finalize' | 'credential' | 'complete'

export type ShoulderPressUploadEvent = {
  phase?: ShoulderPressUploadPhase
  index: number
  state: PendingShoulderPressSegment['uploadState'] | 'finalized'
  progress?: number
}

export type PendingSegmentUploadDependencies = {
  createVideoSession: (input: {
    actionId: number
    clientSessionId: string
    trainingDate: string
    expectedDurationSeconds: number
  }) => Promise<VideoSessionStatus>
  getVideoSessionStatus: (videoId: number) => Promise<VideoSessionStatus>
  uploadVideoSegment: (input: {
    videoId: number
    index: number
    filePath: string
    durationMs: number
    sizeBytes: number
    onProgress?: (progress: number) => void
  }) => Promise<UploadedVideoSegment>
  finalizeVideoSession: (input: {
    videoId: number
    segmentCount: number
    actualDurationSeconds: number
    note: string
  }) => Promise<VideoSessionStatus>
  saveSession: (session: PendingShoulderPressSession) => void
  deleteSavedFile: (path: string) => Promise<void>
}

type LegacyWorkflowDependencies = {
  now?: () => number
  createIntent?: (input: {
    actionId: number
    sizeBytes: number
    durationSeconds: number
  }) => Promise<VideoSessionStatus>
  uploadVideo?: (input: Record<string, unknown> & {
    filePath: string
    onProgress?: (progress: number) => void
  }) => Promise<Record<string, string>>
  completeUpload?: (input: Record<string, unknown>) => Promise<unknown>
  savePending?: (pending: PendingShoulderPressUpload) => void
}

export function shoulderPressUploadErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) return '上传失败，请检查网络后重试'
  const message = error.message.trim()
  if (!message || /authorization|bearer|token|secret/i.test(message) || !/[\u3400-\u9fff]/.test(message)) {
    return '上传失败，请检查网络后重试'
  }
  return message
}

function uploadedIndexes(status: VideoSessionStatus): number[] {
  return Array.isArray(status.uploaded_segments)
    ? status.uploaded_segments.filter((index) => Number.isInteger(index) && index >= 0)
    : []
}

function persist(
  session: PendingShoulderPressSession,
  dependencies: Pick<PendingSegmentUploadDependencies, 'saveSession'>
): PendingShoulderPressSession {
  dependencies.saveSession(session)
  return session
}

function updateSegment(
  session: PendingShoulderPressSession,
  index: number,
  update: Partial<PendingShoulderPressSegment>
): PendingShoulderPressSession {
  return {
    ...session,
    segments: session.segments.map((segment) => (
      segment.index === index ? { ...segment, ...update } : segment
    ))
  }
}

async function deleteUploadedLocalFile(
  segment: PendingShoulderPressSegment,
  dependencies: Pick<PendingSegmentUploadDependencies, 'deleteSavedFile'>
): Promise<void> {
  if (!isSegmentReadyForLocalDeletion(segment)) return
  try {
    await dependencies.deleteSavedFile(segment.savedFilePath)
  } catch {
    // Local cleanup is best-effort; uploaded state is the durable truth.
  }
}

export async function runPendingSegmentUploads(
  initialSession: PendingShoulderPressSession,
  dependencies: PendingSegmentUploadDependencies,
  onProgress: (event: ShoulderPressUploadEvent) => void
): Promise<PendingShoulderPressSession> {
  let session: PendingShoulderPressSession = { ...initialSession, lastError: undefined }

  try {
    if (!session.videoId) {
      const created = await dependencies.createVideoSession({
        actionId: session.actionId,
        clientSessionId: session.clientSessionId,
        trainingDate: session.trainingDate,
        expectedDurationSeconds: session.expectedDurationSeconds
      })
      session = persist({ ...session, videoId: created.video_id }, dependencies)
    }

    const status = await dependencies.getVideoSessionStatus(session.videoId)
    const recovered = markServerUploadedSegments(session, uploadedIndexes(status))
    if (JSON.stringify(recovered.segments) !== JSON.stringify(session.segments)) {
      session = persist(recovered, dependencies)
    } else {
      session = recovered
    }

    for (const segment of session.segments) {
      if (segment.uploadState === 'uploaded') continue

      session = persist(updateSegment(session, segment.index, {
        uploadState: 'uploading',
        sha256: undefined
      }), dependencies)
      onProgress({ phase: 'upload', index: segment.index, state: 'uploading', progress: 0 })

      const uploaded = await dependencies.uploadVideoSegment({
        videoId: session.videoId,
        index: segment.index,
        filePath: segment.savedFilePath,
        durationMs: segment.durationMs,
        sizeBytes: segment.sizeBytes,
        onProgress: (progress) => onProgress({
          phase: 'upload',
          index: segment.index,
          state: 'uploading',
          progress
        })
      })

      session = persist(updateSegment(session, segment.index, {
        uploadState: 'uploaded',
        sha256: uploaded.sha256
      }), dependencies)
      onProgress({ phase: 'upload', index: segment.index, state: 'uploaded', progress: 100 })
      await deleteUploadedLocalFile(session.segments[segment.index], dependencies)
    }

    if (!session.finalized) {
      await dependencies.finalizeVideoSession({
        videoId: session.videoId,
        segmentCount: session.segments.length,
        actualDurationSeconds: Math.ceil(session.actualDurationMs / 1000),
        note: ''
      })
      session = persist({ ...session, finalized: true, lastError: undefined }, dependencies)
      onProgress({ phase: 'finalize', index: session.segments.length - 1, state: 'finalized', progress: 100 })
    }

    return session
  } catch (error) {
    const uploading = session.segments.find((segment) => segment.uploadState === 'uploading')
    if (uploading) {
      session = updateSegment(session, uploading.index, {
        uploadState: 'pending',
        sha256: undefined
      })
    }
    persist({ ...session, lastError: shoulderPressUploadErrorMessage(error) }, dependencies)
    throw error
  }
}

export async function runShoulderPressUploadWorkflow(
  initialPending: PendingShoulderPressUpload,
  dependencies: LegacyWorkflowDependencies,
  onEvent: (event: { phase: ShoulderPressUploadPhase; progress: number }) => void
): Promise<PendingShoulderPressUpload> {
  const firstSegment = initialPending.segments[0]
  if (!firstSegment || !dependencies.createIntent || !dependencies.uploadVideo || !dependencies.completeUpload) {
    throw new Error('录像上传信息不完整，请重新开始')
  }

  const intent = await dependencies.createIntent({
    actionId: initialPending.actionId,
    sizeBytes: firstSegment.sizeBytes,
    durationSeconds: Math.ceil(firstSegment.durationMs / 1000)
  })
  const uploaded = await dependencies.uploadVideo({
    filePath: firstSegment.savedFilePath,
    onProgress: (progress) => onEvent({ phase: 'upload', progress })
  })
  await dependencies.completeUpload({
    videoId: intent.video_id,
    hash: uploaded.hash,
    actualDurationMinutes: Math.ceil(initialPending.actualDurationMs / 60000),
    note: ''
  })
  const completed: PendingShoulderPressUpload = {
    ...initialPending,
    videoId: intent.video_id,
    hash: uploaded.hash,
    finalized: true
  }
  dependencies.savePending?.(completed)
  onEvent({ phase: 'complete', progress: 100 })
  return completed
}
