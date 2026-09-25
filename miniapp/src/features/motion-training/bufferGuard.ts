import { MOTION_TRAINING_SEGMENT_DURATION_MS } from './recorder'
import type { PendingMotionTrainingSegment } from './session'

export { MOTION_TRAINING_SEGMENT_DURATION_MS }

export const MOTION_TRAINING_BUFFER_HIGH_BYTES = 65 * 1024 * 1024
export const MOTION_TRAINING_BUFFER_LOW_BYTES = 10 * 1024 * 1024
const MIN_NEXT_SEGMENT_RESERVE_BYTES = 20 * 1024 * 1024

/** Application buffer estimate, not a measurement of the device's free disk. */
export function motionTrainingNextSegmentReserveBytes(segments: PendingMotionTrainingSegment[]): number {
  let reserve = MIN_NEXT_SEGMENT_RESERVE_BYTES
  for (const segment of segments) {
    if (segment.compressionState !== 'compressed') return MOTION_TRAINING_BUFFER_HIGH_BYTES
    reserve = Math.max(reserve, Math.ceil(segment.sizeBytes / segment.durationMs * MOTION_TRAINING_SEGMENT_DURATION_MS * 1.5))
  }
  // An unusually large segment requires draining the entire buffer before continuing.
  return Math.min(reserve, MOTION_TRAINING_BUFFER_HIGH_BYTES)
}

export type MotionTrainingBufferState = 'recording' | 'buffer_paused' | 'buffer_ready'

export type MotionTrainingBufferTransition = {
  state: MotionTrainingBufferState
  alert: 'pause' | 'ready' | null
}

export function pendingMotionTrainingLocalBytes(
  segments: PendingMotionTrainingSegment[]
): number {
  let totalBytes = 0

  for (const segment of segments) {
    if (segment.compressionState !== 'compressed') return Number.POSITIVE_INFINITY
    if (segment.uploadState === 'uploaded' && segment.localFileDeleted) continue
    if (Number.isFinite(segment.sizeBytes) && segment.sizeBytes > 0) {
      totalBytes += segment.sizeBytes
    }
  }

  return totalBytes
}

export function nextMotionTrainingBufferTransition(input: {
  state: MotionTrainingBufferState
  pendingBytes: number
  reserveBytes?: number
}): MotionTrainingBufferTransition {
  if (
    input.state === 'recording' &&
    input.pendingBytes > 0 && input.pendingBytes + (input.reserveBytes ?? MIN_NEXT_SEGMENT_RESERVE_BYTES) >= MOTION_TRAINING_BUFFER_HIGH_BYTES
  ) {
    return { state: 'buffer_paused', alert: 'pause' }
  }
  if (
    input.state === 'buffer_paused' &&
    canResumeMotionTrainingFromBuffer(input.pendingBytes, input.reserveBytes)
  ) {
    return { state: 'buffer_ready', alert: 'ready' }
  }
  return { state: input.state, alert: null }
}

export function canResumeMotionTrainingFromBuffer(pendingBytes: number, reserveBytes = MIN_NEXT_SEGMENT_RESERVE_BYTES): boolean {
  return pendingBytes < MOTION_TRAINING_BUFFER_LOW_BYTES && pendingBytes + reserveBytes <= MOTION_TRAINING_BUFFER_HIGH_BYTES
}
