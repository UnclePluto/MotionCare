import { describe, expect, it } from 'vitest'

import {
  canResumeMotionTrainingFromBuffer,
  motionTrainingNextSegmentReserveBytes,
  motionTrainingSegmentDurationMs,
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
  it('counts uploaded files until their deletion is confirmed', () => {
    expect(pendingMotionTrainingLocalBytes([
      compressedSegment({ sizeBytes: 7 * MB, uploadState: 'pending' }),
      compressedSegment({ sizeBytes: 8 * MB, uploadState: 'uploading' }),
      compressedSegment({ sizeBytes: 9 * MB, uploadState: 'uploaded', sha256: 'ok' })
    ])).toBe(24 * MB)
    expect(pendingMotionTrainingLocalBytes([
      compressedSegment({ sizeBytes: 9 * MB, uploadState: 'uploaded', localFileDeleted: true })
    ])).toBe(0)
  })

  it('reserves a full minute from observed bitrate before admitting another segment', () => {
    const reserve = motionTrainingNextSegmentReserveBytes([
      compressedSegment({ durationMs: 60_000, sizeBytes: 20 * MB })
    ])
    expect(reserve).toBe(30 * MB)
    expect(nextMotionTrainingBufferTransition({ state: 'recording', pendingBytes: 36 * MB, reserveBytes: reserve }))
      .toEqual({ state: 'buffer_paused', alert: 'pause' })
    expect(nextMotionTrainingBufferTransition({ state: 'recording', pendingBytes: 34 * MB, reserveBytes: reserve }))
      .toEqual({ state: 'recording', alert: null })
    expect(canResumeMotionTrainingFromBuffer(9 * MB, 60 * MB)).toBe(false)
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

it('keeps 60 seconds normally and selects 30 seconds when a minute would exceed 25 MiB', () => {
  expect(motionTrainingSegmentDurationMs([])).toBe(60_000)
  expect(motionTrainingSegmentDurationMs([compressedSegment({ durationMs: 60_000, sizeBytes: 25 * MB })])).toBe(60_000)
  const large = compressedSegment({ durationMs: 60_000, sizeBytes: 40 * MB })
  expect(motionTrainingSegmentDurationMs([large])).toBe(30_000)
  expect(motionTrainingNextSegmentReserveBytes([large])).toBe(30 * MB)
  expect(motionTrainingSegmentDurationMs([large, compressedSegment({ durationMs: 30_000, sizeBytes: 10 * MB })])).toBe(30_000)
})

it('blocks another recording even with an empty queue if its estimated file cannot fit', () => {
  const reserve = motionTrainingNextSegmentReserveBytes([compressedSegment({ durationMs: 30_000, sizeBytes: 70 * MB })])
  expect(reserve).toBeGreaterThan(65 * MB)
  expect(nextMotionTrainingBufferTransition({ state: 'recording', pendingBytes: 0, reserveBytes: reserve }).state).toBe('buffer_paused')
  expect(canResumeMotionTrainingFromBuffer(0, reserve)).toBe(false)
})

it('does not offer resume when the next file consumes the entire budget', () => {
  expect(canResumeMotionTrainingFromBuffer(0, 65 * MB)).toBe(false)
})
