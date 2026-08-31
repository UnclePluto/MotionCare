import { MOTION_TRAINING_SEGMENT_DURATION_MS } from './recorder'
import type { PendingMotionTrainingSegment } from './session'

export { MOTION_TRAINING_SEGMENT_DURATION_MS }

export const MOTION_TRAINING_BUFFER_HIGH_BYTES = 65 * 1024 * 1024
export const MOTION_TRAINING_BUFFER_LOW_BYTES = 10 * 1024 * 1024

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
    if (segment.uploadState === 'uploaded') continue
    if (Number.isFinite(segment.sizeBytes) && segment.sizeBytes > 0) {
      totalBytes += segment.sizeBytes
    }
  }

  return totalBytes
}

export function nextMotionTrainingBufferTransition(input: {
  state: MotionTrainingBufferState
  pendingBytes: number
}): MotionTrainingBufferTransition {
  if (
    input.state === 'recording' &&
    input.pendingBytes >= MOTION_TRAINING_BUFFER_HIGH_BYTES
  ) {
    return { state: 'buffer_paused', alert: 'pause' }
  }
  if (
    input.state === 'buffer_paused' &&
    input.pendingBytes < MOTION_TRAINING_BUFFER_LOW_BYTES
  ) {
    return { state: 'buffer_ready', alert: 'ready' }
  }
  return { state: input.state, alert: null }
}

export function canResumeMotionTrainingFromBuffer(pendingBytes: number): boolean {
  return pendingBytes < MOTION_TRAINING_BUFFER_LOW_BYTES
}
