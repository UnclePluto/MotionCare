import { motionTrainingNextSegmentReserveBytes, pendingMotionTrainingLocalBytes } from './bufferGuard'
import { createRecordingTrace } from './recordingTrace'
import { isCompressedMotionTrainingSegment, type PendingMotionTrainingSession } from './session'

type Event = 'save_call' | 'save_success' | 'save_failure' | 'preflight_call' | 'preflight_failure' | 'preflight_success' | 'access_call' | 'access_exists' | 'access_failure' | 'cleanup_call' | 'cleanup_success' | 'cleanup_failure' | 'upload_call' | 'upload_success' | 'upload_failure' | 'buffer_paused' | 'buffer_ready' | 'page_hide' | 'page_show'

// Only allowlisted fields are exported. Neither session identities nor file paths
// or raw native messages belong in a shareable diagnostic journal.
export function createSegmentTrace(now = Date.now, environment: object = {}) {
  const startedAt = now()
  const recording = createRecordingTrace(now, environment)
  const events: object[] = []
  return {
    recording,
    mark(event: Event, segment?: number, error?: unknown) {
      const value = error && typeof error === 'object' ? error as { errCode?: unknown; errMsg?: unknown; message?: unknown } : {}
      const text = typeof value.errMsg === 'string' ? value.errMsg : typeof value.message === 'string' ? value.message : ''
      const reason = error === undefined ? undefined : /permission|auth|denied|not permitted/i.test(text) ? 'permission'
        : /ENOENT|not exist|not found|no such file/i.test(text) ? 'missing'
          : /timeout/i.test(text) ? 'timeout' : /quota|space|storage.*full/i.test(text) ? 'storage_full' : 'unknown'
      const code = typeof value.errCode === 'number' && Number.isSafeInteger(value.errCode) ? value.errCode : undefined
      events.push({ event, elapsedMs: Math.max(0, now() - startedAt), segment, code, reason })
      if (events.length > 400) events.shift()
    },
    export(session: PendingMotionTrainingSession | null, bufferState: string) {
      const segments = session?.segments ?? []
      return JSON.stringify({ schema: 1, build: 'minute-segments-managed-files-1',
        recording: JSON.parse(recording.export()), events,
        snapshot: { bufferState, videoId: session?.videoId,
          pendingLocalBytes: Number.isFinite(pendingMotionTrainingLocalBytes(segments)) ? pendingMotionTrainingLocalBytes(segments) : 'unknown',
          reserveBytes: motionTrainingNextSegmentReserveBytes(segments),
          uploadedUncleanedBytes: segments.reduce((sum, segment) => sum + (isCompressedMotionTrainingSegment(segment) && segment.uploadState === 'uploaded' && !segment.localFileDeleted ? segment.sizeBytes : 0), 0),
          segments: segments.map(segment => isCompressedMotionTrainingSegment(segment)
            ? { index: segment.index, sizeBytes: segment.sizeBytes, durationMs: segment.durationMs, uploadState: segment.uploadState, localFileState: segment.localFileState ?? 'saved', localFileDeleted: segment.localFileDeleted === true }
            : { index: segment.index, compressionState: segment.compressionState }) }
      })
    }
  }
}

// Keep only the current recording's journal; retries use the same journal.
let current: { id: string; trace: ReturnType<typeof createSegmentTrace> } | undefined
export function segmentTraceFor(id: string, environment: object = {}) {
  if (current?.id !== id) current = { id, trace: createSegmentTrace(Date.now, environment) }
  return current.trace
}
