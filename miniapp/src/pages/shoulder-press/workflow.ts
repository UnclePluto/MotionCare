import { containsSensitiveCredentialText } from '../../api/safeError'
import type { UploadedVideoSegment, VideoSessionStatus } from './api'
import {
  isCompressedShoulderPressSegment,
  isSegmentReadyForLocalDeletion,
  markServerUploadedSegments,
  type CompressedShoulderPressSegment,
  type PendingShoulderPressSegment,
  type PendingShoulderPressSession,
  type PendingShoulderPressUpload
} from './session'

export type ShoulderPressUploadPhase = 'session' | 'status' | 'upload' | 'finalize' | 'credential' | 'complete'

export type ShoulderPressUploadEvent = {
  phase?: ShoulderPressUploadPhase
  index: number
  state: 'pending' | 'uploading' | 'uploaded' | 'finalized'
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
    clientSessionId: string
    trainingDate: string
  }) => Promise<VideoSessionStatus>
  getVideoSessionStatus?: PendingSegmentUploadDependencies['getVideoSessionStatus']
  uploadVideoSegment?: PendingSegmentUploadDependencies['uploadVideoSegment']
  finalizeVideoSession?: PendingSegmentUploadDependencies['finalizeVideoSession']
  deleteSavedFile?: PendingSegmentUploadDependencies['deleteSavedFile']
  uploadVideo?: (input: Record<string, unknown> & {
    filePath: string
    onProgress?: (progress: number) => void
  }) => Promise<Record<string, string>>
  completeUpload?: (input: Record<string, unknown>) => Promise<unknown>
  savePending?: (pending: PendingShoulderPressUpload) => void
}

const REMOTE_SEGMENTS_ERROR_MESSAGE = '服务端分段状态不一致，请重新上传'

export function shoulderPressUploadErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) return '上传失败，请检查网络后重试'
  const message = error.message.trim()
  if (!message || containsSensitiveCredentialText(message) || !/[\u3400-\u9fff]/.test(message)) {
    return '上传失败，请检查网络后重试'
  }
  return message
}

function uploadedIndexes(status: VideoSessionStatus, segmentCount: number): number[] {
  if (status.uploaded_segments === undefined) return []
  if (!Array.isArray(status.uploaded_segments)) throw new Error(REMOTE_SEGMENTS_ERROR_MESSAGE)

  const seen = new Set<number>()
  for (const index of status.uploaded_segments) {
    if (!Number.isInteger(index) || index < 0 || index >= segmentCount || seen.has(index)) {
      throw new Error(REMOTE_SEGMENTS_ERROR_MESSAGE)
    }
    seen.add(index)
  }

  const indexes = [...seen].sort((left, right) => left - right)
  for (let expected = 0; expected < indexes.length; expected += 1) {
    if (indexes[expected] !== expected) throw new Error(REMOTE_SEGMENTS_ERROR_MESSAGE)
  }
  return indexes
}

function persist(
  session: PendingShoulderPressSession,
  dependencies: Pick<PendingSegmentUploadDependencies, 'saveSession'>
): PendingShoulderPressSession {
  dependencies.saveSession(session)
  return session
}

function updateCompressedSegment(
  session: PendingShoulderPressSession,
  index: number,
  update: Partial<CompressedShoulderPressSegment>
): PendingShoulderPressSession {
  return {
    ...session,
    segments: session.segments.map((segment) => (
      segment.index === index && isCompressedShoulderPressSegment(segment)
        ? { ...segment, ...update }
        : segment
    ))
  }
}

async function deleteUploadedLocalFile(
  segment: CompressedShoulderPressSegment,
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
    if (session.segments.some((segment) => !isCompressedShoulderPressSegment(segment))) {
      throw new Error('录像分段尚未压缩，请重试')
    }

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
    const recovered = markServerUploadedSegments(session, uploadedIndexes(status, session.segments.length))
    if (JSON.stringify(recovered.segments) !== JSON.stringify(session.segments)) {
      session = persist(recovered, dependencies)
    } else {
      session = recovered
    }

    for (const segment of session.segments) {
      if (!isCompressedShoulderPressSegment(segment)) {
        throw new Error('录像分段尚未压缩，请重试')
      }
      if (segment.uploadState === 'uploaded') continue

      session = persist(updateCompressedSegment(session, segment.index, {
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

      session = persist(updateCompressedSegment(session, segment.index, {
        uploadState: 'uploaded',
        sha256: uploaded.sha256
      }), dependencies)
      onProgress({ phase: 'upload', index: segment.index, state: 'uploaded', progress: 100 })
      const uploadedSegment = session.segments[segment.index]
      if (uploadedSegment && isCompressedShoulderPressSegment(uploadedSegment)) {
        await deleteUploadedLocalFile(uploadedSegment, dependencies)
      }
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
    const uploading = session.segments.find((segment) => (
      isCompressedShoulderPressSegment(segment) && segment.uploadState === 'uploading'
    ))
    if (uploading) {
      session = updateCompressedSegment(session, uploading.index, {
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
  if (
    initialPending.segments.length !== 1 ||
    !firstSegment ||
    !isCompressedShoulderPressSegment(firstSegment) ||
    !firstSegment.savedFilePath ||
    !Number.isInteger(firstSegment.durationMs) ||
    firstSegment.durationMs <= 0 ||
    !Number.isInteger(firstSegment.sizeBytes) ||
    firstSegment.sizeBytes <= 0
  ) {
    throw new Error('录像上传信息不完整，请重新开始')
  }

  let videoId = initialPending.videoId
  if (!videoId) {
    if (!dependencies.createIntent) throw new Error('录像上传信息不完整，请重新开始')
    onEvent({ phase: 'credential', progress: 0 })
    const intent = await dependencies.createIntent({
      actionId: initialPending.actionId,
      sizeBytes: firstSegment.sizeBytes,
      durationSeconds: Math.ceil(firstSegment.durationMs / 1000),
      clientSessionId: initialPending.clientSessionId,
      trainingDate: initialPending.trainingDate
    })
    videoId = intent.video_id
  }

  if (!Number.isInteger(videoId) || videoId <= 0) throw new Error('录像上传信息不完整，请重新开始')

  const pendingSession: PendingShoulderPressSession = {
    clientSessionId: initialPending.clientSessionId,
    videoId,
    actionId: initialPending.actionId,
    trainingDate: initialPending.trainingDate,
    expectedDurationSeconds: initialPending.expectedDurationSeconds,
    actualDurationMs: firstSegment.durationMs,
    segments: [{
      ...firstSegment,
      index: 0,
      uploadState: firstSegment.uploadState === 'uploaded' ? 'uploaded' : 'pending'
    }],
    finalized: false,
    createdAt: initialPending.createdAt
  }

  const toLegacyPending = (session: PendingShoulderPressSession): PendingShoulderPressUpload => {
    const segment = session.segments[0]
    if (!segment || !isCompressedShoulderPressSegment(segment)) {
      throw new Error('录像上传信息不完整，请重新开始')
    }
    return {
      ...initialPending,
      ...session,
      tempFilePath: segment.savedFilePath,
      durationSeconds: Math.max(1, Math.round(segment.durationMs / 1000)),
      sizeBytes: segment.sizeBytes,
      ...(segment.sha256 ? { hash: segment.sha256 } : {})
    }
  }

  const apiDependencies = (
    dependencies.getVideoSessionStatus &&
    dependencies.uploadVideoSegment &&
    dependencies.finalizeVideoSession
  )
    ? null
    : await import('./api')

  const completedSession = await runPendingSegmentUploads(pendingSession, {
    createVideoSession: async () => ({ video_id: videoId, status: 'created' }),
    getVideoSessionStatus: dependencies.getVideoSessionStatus ?? apiDependencies.getVideoSessionStatus,
    uploadVideoSegment: dependencies.uploadVideoSegment ?? apiDependencies.uploadVideoSegment,
    finalizeVideoSession: dependencies.finalizeVideoSession ?? apiDependencies.finalizeVideoSession,
    saveSession: (session) => dependencies.savePending?.(toLegacyPending(session)),
    deleteSavedFile: dependencies.deleteSavedFile ?? (async () => undefined)
  }, (event) => {
    if (event.phase === 'upload') onEvent({ phase: 'upload', progress: event.progress ?? 0 })
    if (event.phase === 'finalize') onEvent({ phase: 'finalize', progress: event.progress ?? 100 })
  })

  const completed = toLegacyPending(completedSession)
  dependencies.savePending?.(completed)
  onEvent({ phase: 'complete', progress: 100 })
  return completed
}
