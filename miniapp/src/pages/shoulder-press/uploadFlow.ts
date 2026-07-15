import {
  clearShoulderPressSession,
  loadShoulderPressSession,
  saveShoulderPressSession,
  type StorageLike,
} from './session'

type UploadFlowStatus = {
  status: string
  uploaded_segment_count?: number
  processing?: null | { status: string; progress_percent: number }
  training_record_id?: number | null
}

type UploadFlowUpdate = {
  stage: 'uploading' | 'processing'
  uploadedSegmentCount: number
  segmentCount: number
  processingStatus?: string
  progressPercent: number
}

type UploadFlowOptions = {
  storage: StorageLike
  drainSegments: () => Promise<void>
  finish: (input: {
    videoId: number
    segmentCount: number
    durationSeconds: number
    trainingDate: string
  }) => Promise<unknown>
  getStatus: (videoId: number) => Promise<UploadFlowStatus>
  sleep: (milliseconds: number) => Promise<void>
  onUpdate?: (update: UploadFlowUpdate) => void
  isCancelled?: () => boolean
}

function dateFromTimestamp(timestamp: number): string {
  const date = new Date(timestamp)
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 10)
}

export async function runShoulderPressUploadFlow(
  options: UploadFlowOptions,
): Promise<'succeeded' | 'expired' | 'unrecoverable' | 'cancelled'> {
  while (!options.isCancelled?.()) {
    let session = loadShoulderPressSession(options.storage)
    if (!session) throw new Error('未找到待保存的训练录像')
    if (session.phase === 'recording') {
      const recoveredCount = session.segmentCount ?? Math.max(
        0,
        ...session.segments.map((item) => item.sequenceIndex + 1),
      )
      if (recoveredCount === 0) {
        session = {
          ...session,
          phase: 'uploading',
          unrecoverableReason: '未保存到有效录像分片，请重新训练',
        }
        saveShoulderPressSession(options.storage, session)
        return 'unrecoverable'
      }
      session = {
        ...session,
        phase: 'uploading',
        segmentCount: recoveredCount,
        trainingDate: session.trainingDate ?? dateFromTimestamp(session.startedAt),
      }
      saveShoulderPressSession(options.storage, session)
    }

    const segmentCount = session.segmentCount ?? 0
    if (session.segments.length > 0) {
      options.onUpdate?.({
        stage: 'uploading',
        uploadedSegmentCount: Math.max(0, segmentCount - session.segments.length),
        segmentCount,
        progressPercent: segmentCount > 0
          ? Math.round(((segmentCount - session.segments.length) / segmentCount) * 60)
          : 0,
      })
      await options.drainSegments()
      const remaining = loadShoulderPressSession(options.storage)?.segments.length ?? 0
      if (remaining > 0) await options.sleep(1_000)
      continue
    }

    if (session.unrecoverableReason) return 'unrecoverable'

    if (session.phase === 'uploading') {
      if (!session.segmentCount || !session.trainingDate) {
        throw new Error('训练录像结束信息不完整')
      }
      await options.finish({
        videoId: session.videoId,
        segmentCount: session.segmentCount,
        durationSeconds: Math.max(session.durationSeconds, 1),
        trainingDate: session.trainingDate,
      })
      session = { ...session, phase: 'processing' }
      saveShoulderPressSession(options.storage, session)
    }

    const status = await options.getStatus(session.videoId)
    if (status.status === 'attached' && status.training_record_id) {
      clearShoulderPressSession(options.storage)
      return 'succeeded'
    }
    if (status.status === 'expired') return 'expired'
    options.onUpdate?.({
      stage: 'processing',
      uploadedSegmentCount: session.segmentCount ?? 0,
      segmentCount: session.segmentCount ?? 0,
      processingStatus: status.processing?.status ?? status.status,
      progressPercent: Math.max(60, status.processing?.progress_percent ?? 60),
    })
    await options.sleep(2_000)
  }
  return 'cancelled'
}
