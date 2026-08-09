import { SHOULDER_PRESS_SEGMENT_DURATION_MS } from './recorder'
import type { PendingShoulderPressSegment } from './session'

export { SHOULDER_PRESS_SEGMENT_DURATION_MS }

export const SHOULDER_PRESS_BUFFER_HIGH_BYTES = 65 * 1024 * 1024
export const SHOULDER_PRESS_BUFFER_LOW_BYTES = 10 * 1024 * 1024

export type ShoulderPressBufferState = 'recording' | 'buffer_paused' | 'buffer_ready'

export type ShoulderPressBufferTransition = {
  state: ShoulderPressBufferState
  alert: 'pause' | 'ready' | null
}

export function pendingShoulderPressLocalBytes(
  segments: PendingShoulderPressSegment[]
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

export function nextShoulderPressBufferTransition(input: {
  state: ShoulderPressBufferState
  pendingBytes: number
}): ShoulderPressBufferTransition {
  if (
    input.state === 'recording' &&
    input.pendingBytes >= SHOULDER_PRESS_BUFFER_HIGH_BYTES
  ) {
    return { state: 'buffer_paused', alert: 'pause' }
  }
  if (
    input.state === 'buffer_paused' &&
    input.pendingBytes < SHOULDER_PRESS_BUFFER_LOW_BYTES
  ) {
    return { state: 'buffer_ready', alert: 'ready' }
  }
  return { state: input.state, alert: null }
}

export function canResumeShoulderPressFromBuffer(pendingBytes: number): boolean {
  return pendingBytes < SHOULDER_PRESS_BUFFER_LOW_BYTES
}
