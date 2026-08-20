import { describe, expect, it } from 'vitest'

import {
  canResumeMotionTrainingFromBuffer,
  nextMotionTrainingBufferTransition,
  pendingMotionTrainingLocalBytes
} from './bufferGuard'
import type { CompressedMotionTrainingSegment } from './session'

const MB = 1024 * 1024

function compressedSegment(
  overrides: Partial<CompressedMotionTrainingSegment>
): CompressedMotionTrainingSegment {
  return {
    index: 0,
    compressionState: 'compressed',
    savedFilePath: 'wxfile://store/segment.mp4',
    durationMs: 5_000,
    sizeBytes: MB,
    uploadState: 'pending',
    ...overrides
  }
}

describe('shoulder-press buffer guard', () => {
  it('counts only segments that still depend on a local file', () => {
    expect(pendingMotionTrainingLocalBytes([
      compressedSegment({ sizeBytes: 7 * MB, uploadState: 'pending' }),
      compressedSegment({ sizeBytes: 8 * MB, uploadState: 'uploading' }),
      compressedSegment({ sizeBytes: 9 * MB, uploadState: 'uploaded', sha256: 'ok' })
    ])).toBe(15 * MB)
  })

  it('pauses once at 65MB and becomes ready only below 10MB', () => {
    expect(nextMotionTrainingBufferTransition({ state: 'recording', pendingBytes: 65 * MB }))
      .toEqual({ state: 'buffer_paused', alert: 'pause' })
    expect(nextMotionTrainingBufferTransition({ state: 'buffer_paused', pendingBytes: 10 * MB }))
      .toEqual({ state: 'buffer_paused', alert: null })
    expect(nextMotionTrainingBufferTransition({ state: 'buffer_paused', pendingBytes: 10 * MB - 1 }))
      .toEqual({ state: 'buffer_ready', alert: 'ready' })
    expect(nextMotionTrainingBufferTransition({ state: 'buffer_ready', pendingBytes: 0 }))
      .toEqual({ state: 'buffer_ready', alert: null })
    expect(canResumeMotionTrainingFromBuffer(10 * MB)).toBe(false)
    expect(canResumeMotionTrainingFromBuffer(10 * MB - 1)).toBe(true)
  })

  it('treats a legacy local segment with unknown size as unsafe', () => {
    expect(pendingMotionTrainingLocalBytes([
      {
        index: 0,
        compressionState: 'pending_compression',
        rawSavedFilePath: 'wxfile://store/legacy.mp4',
        durationMs: 5_000
      }
    ])).toBe(Number.POSITIVE_INFINITY)
  })
})
