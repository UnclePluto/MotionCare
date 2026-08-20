import { describe, expect, it, vi } from 'vitest'

import {
  LEGACY_PENDING_MOTION_TRAINING_SESSION_KEY,
  PENDING_MOTION_TRAINING_SESSION_KEY,
  appendUploadableMotionTrainingSegment,
  appendPendingSegment,
  buildMotionTrainingCameraUrl,
  buildMotionTrainingPreviewUrl,
  buildMotionTrainingSessionUrl,
  buildMotionTrainingUploadUrl,
  clearPendingMotionTrainingSession,
  clientTrainingMoment,
  createPendingMotionTrainingSession,
  isCompressedMotionTrainingSegment,
  isSegmentReadyForLocalDeletion,
  loadPendingMotionTrainingSession,
  markServerUploadedSegments,
  markMotionTrainingEnded,
  markMotionTrainingStarted,
  promoteLegacyMotionTrainingSegment,
  requireMotionTrainingStartedAt,
  savePendingMotionTrainingSession
} from './session'

function memoryStorage(initial?: unknown) {
  const store = new Map<string, unknown>()
  if (initial !== undefined) store.set(PENDING_MOTION_TRAINING_SESSION_KEY, initial)
  return {
    getStorageSync: vi.fn((key: string) => store.get(key)),
    setStorageSync: vi.fn((key: string, value: unknown) => store.set(key, value)),
    removeStorageSync: vi.fn((key: string) => store.delete(key))
  }
}

describe('shoulder press segmented session helpers', () => {
  it('builds session, preview, and upload urls', () => {
    expect(buildMotionTrainingSessionUrl(42)).toBe('/pages/motion-training/index?actionId=42')
    expect(buildMotionTrainingCameraUrl(42)).toBe('/pages/motion-training/camera?actionId=42')
    expect(buildMotionTrainingPreviewUrl(42)).toBe(
      '/pages/motion-training/preview?actionId=42'
    )
    expect(buildMotionTrainingUploadUrl()).toBe('/pages/motion-training/upload')
  })

  it('formats the phone instant with an explicit local offset', () => {
    expect(clientTrainingMoment(Date.UTC(2026, 7, 5, 16, 1, 2), 480)).toEqual({
      trainingDate: '2026-08-06',
      timestamp: '2026-08-06T00:01:02+08:00'
    })
  })

  it('sets the first start once and refreshes a stale pre-midnight training date', () => {
    const session = createPendingMotionTrainingSession({
      actionId: 42,
      expectedDurationSeconds: 180,
      trainingDate: '2026-08-05',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: Date.UTC(2026, 7, 5, 15, 59, 0)
    })

    const started = markMotionTrainingStarted(
      session,
      Date.UTC(2026, 7, 5, 16, 1, 2),
      480
    )
    const resumed = markMotionTrainingStarted(
      started,
      Date.UTC(2026, 7, 5, 16, 5, 0),
      480
    )

    expect(started.trainingDate).toBe('2026-08-06')
    expect(started.trainingStartedAt).toBe('2026-08-06T00:01:02+08:00')
    expect(resumed.trainingStartedAt).toBe(started.trainingStartedAt)
  })

  it('requires a recorded training start before creating a remote session', () => {
    const session = createPendingMotionTrainingSession({
      actionId: 42,
      expectedDurationSeconds: 180,
      trainingDate: '2026-08-06',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: Date.UTC(2026, 7, 5, 16, 0, 0)
    })

    expect(() => requireMotionTrainingStartedAt(session))
      .toThrow('训练开始时间缺失，请重新训练')
    expect(requireMotionTrainingStartedAt({
      ...session,
      trainingStartedAt: '2026-08-06T00:01:02+08:00'
    })).toBe('2026-08-06T00:01:02+08:00')
  })

  it('sets the final end once and keeps it through storage recovery', () => {
    const started = markMotionTrainingStarted(createPendingMotionTrainingSession({
      actionId: 42,
      expectedDurationSeconds: 180,
      trainingDate: '2026-08-05',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: Date.UTC(2026, 7, 5, 15, 59, 0)
    }), Date.UTC(2026, 7, 5, 16, 1, 2), 480)
    const storage = memoryStorage()
    const ended = markMotionTrainingEnded(started, Date.UTC(2026, 7, 5, 16, 9, 27), 480)

    savePendingMotionTrainingSession(storage, ended)

    expect(loadPendingMotionTrainingSession(storage)).toMatchObject({
      trainingStartedAt: '2026-08-06T00:01:02+08:00',
      trainingEndedAt: '2026-08-06T00:09:27+08:00'
    })
    expect(markMotionTrainingEnded(
      ended,
      Date.UTC(2026, 7, 5, 16, 10, 0),
      480
    ).trainingEndedAt).toBe('2026-08-06T00:09:27+08:00')
  })

  it('rejects ending without a start and rejects a non-increasing end', () => {
    const session = createPendingMotionTrainingSession({
      actionId: 42,
      expectedDurationSeconds: 180,
      trainingDate: '2026-08-06',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: Date.UTC(2026, 7, 5, 16, 0, 0)
    })

    expect(() => markMotionTrainingEnded(
      session,
      Date.UTC(2026, 7, 5, 16, 9, 27),
      480
    )).toThrow('训练开始时间缺失')
    expect(() => markMotionTrainingEnded({
      ...session,
      trainingStartedAt: '2026-08-06T00:09:27+08:00'
    }, Date.UTC(2026, 7, 5, 16, 1, 2), 480)).toThrow('训练结束时间必须晚于开始时间')
  })

  it('keeps legacy manifests valid but rejects malformed offset timestamps', () => {
    const legacyManifest = {
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      actionId: 42,
      trainingDate: '2026-08-06',
      expectedDurationSeconds: 180,
      actualDurationMs: 0,
      segments: [],
      finalized: false,
      createdAt: Date.UTC(2026, 7, 5, 16, 0, 0)
    }

    expect(loadPendingMotionTrainingSession(memoryStorage(legacyManifest))).not.toBeNull()
    expect(loadPendingMotionTrainingSession(memoryStorage({
      ...legacyManifest,
      trainingStartedAt: '2026-08-06T00:01:02'
    }))).toBeNull()
  })

  it.each([
    ['a non-existent calendar date', '2026-02-29T00:01:02+08:00'],
    ['an out-of-range hour', '2026-08-06T24:01:02+08:00'],
    ['an out-of-range minute', '2026-08-06T00:60:02+08:00'],
    ['an out-of-range second', '2026-08-06T00:01:60+08:00'],
    ['an out-of-range offset hour', '2026-08-06T00:01:02+24:00'],
    ['an out-of-range offset minute', '2026-08-06T00:01:02+08:60']
  ])('rejects %s during cold recovery', (_caseName, trainingStartedAt) => {
    expect(loadPendingMotionTrainingSession(memoryStorage({
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      actionId: 42,
      trainingDate: '2026-08-06',
      trainingStartedAt,
      expectedDurationSeconds: 180,
      actualDurationMs: 0,
      segments: [],
      finalized: false,
      createdAt: Date.UTC(2026, 7, 5, 16, 0, 0)
    }))).toBeNull()
  })

  it.each([
    ['the same instant', '2026-08-05T16:00:00Z'],
    ['an earlier instant', '2026-08-05T15:59:59Z']
  ])('rejects %s as the cold-recovery end', (_caseName, trainingEndedAt) => {
    expect(loadPendingMotionTrainingSession(memoryStorage({
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      actionId: 42,
      trainingDate: '2026-08-06',
      trainingStartedAt: '2026-08-06T00:00:00+08:00',
      trainingEndedAt,
      expectedDurationSeconds: 180,
      actualDurationMs: 0,
      segments: [],
      finalized: false,
      createdAt: Date.UTC(2026, 7, 5, 16, 0, 0)
    }))).toBeNull()
  })

  it('rejects cold recovery when the platform timestamp parser is non-finite', () => {
    const parse = vi.spyOn(Date, 'parse').mockReturnValue(Number.NaN)
    try {
      expect(loadPendingMotionTrainingSession(memoryStorage({
        clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
        actionId: 42,
        trainingDate: '2026-08-06',
        trainingStartedAt: '2026-08-06T00:00:00+08:00',
        trainingEndedAt: '2026-08-06T00:01:00+08:00',
        expectedDurationSeconds: 180,
        actualDurationMs: 0,
        segments: [],
        finalized: false,
        createdAt: Date.UTC(2026, 7, 5, 16, 0, 0)
      }))).toBeNull()
    } finally {
      parse.mockRestore()
    }
  })

  it('persists multiple saved segments and converts getVideoInfo kB to bytes', () => {
    const session = createPendingMotionTrainingSession({
      actionId: 42,
      expectedDurationSeconds: 180,
      trainingDate: '2026-07-11',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: 1783692000000
    })
    const updated = appendPendingSegment(session, {
      savedFilePath: 'wxfile://store/segment-0.mp4',
      durationSeconds: 29.8,
      sizeKb: 2048
    })

    expect(updated.segments[0]).toMatchObject({
      index: 0,
      compressionState: 'compressed',
      durationMs: 29800,
      sizeBytes: 2097152,
      uploadState: 'pending'
    })
    expect(updated.actualDurationMs).toBe(29800)
    expect(updated.trainingDate).toBe('2026-07-11')
  })

  it('appends a temporary raw segment with exact duration and byte size', () => {
    const session = createPendingMotionTrainingSession({
      actionId: 42,
      expectedDurationSeconds: 180,
      trainingDate: '2026-07-11',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: 1783692000000
    })

    const updated = appendUploadableMotionTrainingSegment(session, {
      filePath: 'wxfile://temp/raw-segment-0.mp4',
      durationMs: 15_001,
      sizeBytes: 19_876_543,
      localFileState: 'temporary'
    })

    expect(updated.segments[0]).toEqual({
      index: 0,
      compressionState: 'compressed',
      savedFilePath: 'wxfile://temp/raw-segment-0.mp4',
      durationMs: 15_001,
      sizeBytes: 19_876_543,
      uploadState: 'pending',
      localFileState: 'temporary'
    })
    expect(updated.actualDurationMs).toBe(15_001)
  })

  it('allows 1800 seconds and rejects a manifest duration above 1800000ms', () => {
    const session = createPendingMotionTrainingSession({
      actionId: 42,
      expectedDurationSeconds: 1800,
      trainingDate: '2026-07-11',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: 1783692000000
    })

    const full = appendUploadableMotionTrainingSegment(session, {
      filePath: 'wxfile://temp/raw-0.mp4',
      durationMs: 1_800_000,
      sizeBytes: 1,
      localFileState: 'temporary'
    })

    expect(full.actualDurationMs).toBe(1_800_000)
    expect(() => appendUploadableMotionTrainingSegment(session, {
      filePath: 'wxfile://temp/raw-1.mp4',
      durationMs: 1_800_001,
      sizeBytes: 1,
      localFileState: 'temporary'
    })).toThrow('录像总时长超过限制')
  })

  it('promotes a legacy pending-compression segment without changing its index', () => {
    const base = createPendingMotionTrainingSession({
      actionId: 42,
      expectedDurationSeconds: 180,
      trainingDate: '2026-07-11',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: 1783692000000
    })
    const pending = {
      ...base,
      actualDurationMs: 29_800,
      segments: [{
        index: 0,
        compressionState: 'pending_compression' as const,
        rawSavedFilePath: 'wxfile://store/raw-0.mp4',
        durationMs: 29_800
      }]
    }

    expect(pending.actualDurationMs).toBe(29_800)
    expect(pending.segments[0]).toEqual({
      index: 0,
      compressionState: 'pending_compression',
      rawSavedFilePath: 'wxfile://store/raw-0.mp4',
      durationMs: 29_800
    })

    const completed = promoteLegacyMotionTrainingSegment(pending, 0, {
      savedFilePath: 'wxfile://store/raw-0.mp4',
      durationMs: 29_800,
      sizeBytes: 2_097_152
    })

    expect(completed.actualDurationMs).toBe(29_800)
    expect(completed.segments[0]).toEqual({
      index: 0,
      compressionState: 'compressed',
      savedFilePath: 'wxfile://store/raw-0.mp4',
      durationMs: 29_800,
      sizeBytes: 2_097_152,
      uploadState: 'pending',
      localFileState: 'saved'
    })
    expect(isCompressedMotionTrainingSegment(completed.segments[0])).toBe(true)
  })

  it('loads the raw path and error from a legacy compression-failed manifest', () => {
    const restored = loadPendingMotionTrainingSession(memoryStorage({
      ...createPendingMotionTrainingSession({
      actionId: 42,
      expectedDurationSeconds: 180,
      trainingDate: '2026-07-11',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: 1783692000000
      }),
      actualDurationMs: 30_000,
      segments: [{
        index: 0,
        compressionState: 'compression_failed',
        rawSavedFilePath: 'wxfile://store/raw-0.mp4',
        durationMs: 30_000,
        compressionError: '旧版压缩失败'
      }]
    }))

    expect(restored?.segments[0]).toEqual({
      index: 0,
      compressionState: 'compression_failed',
      rawSavedFilePath: 'wxfile://store/raw-0.mp4',
      durationMs: 30_000,
      compressionError: '旧版压缩失败'
    })
    expect(restored && isCompressedMotionTrainingSegment(restored.segments[0])).toBe(false)
  })

  it('loads old manifests without compressionState as compressed segments', () => {
    const restored = loadPendingMotionTrainingSession(memoryStorage({
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      actionId: 42,
      trainingDate: '2026-07-11',
      expectedDurationSeconds: 180,
      actualDurationMs: 30_000,
      finalized: false,
      createdAt: 1783692000000,
      segments: [{
        index: 0,
        savedFilePath: 'wxfile://store/segment-0.mp4',
        durationMs: 30_000,
        sizeBytes: 1024,
        uploadState: 'pending'
      }]
    }))

    expect(restored?.segments[0]).toMatchObject({
      compressionState: 'compressed',
      savedFilePath: 'wxfile://store/segment-0.mp4',
      uploadState: 'pending',
      localFileState: 'saved'
    })
  })

  it('keeps the original training date when a session is restored on the next day', () => {
    const storage = memoryStorage()
    const session = appendPendingSegment(createPendingMotionTrainingSession({
      actionId: 42,
      expectedDurationSeconds: 180,
      trainingDate: '2026-07-11',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: 1783692000000
    }), {
      savedFilePath: 'wxfile://store/segment-0.mp4',
      durationSeconds: 30,
      sizeKb: 1000
    })

    savePendingMotionTrainingSession(storage, session)

    expect(loadPendingMotionTrainingSession(storage)?.trainingDate).toBe('2026-07-11')
  })

  it('rejects damaged segment metadata and non-contiguous indexes during cold recovery', () => {
    const validBase = {
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      actionId: 42,
      trainingDate: '2026-07-11',
      expectedDurationSeconds: 180,
      actualDurationMs: 60000,
      finalized: false,
      createdAt: 1783692000000
    }

    expect(loadPendingMotionTrainingSession(memoryStorage({
      ...validBase,
      segments: [{
        index: 0,
        savedFilePath: '',
        durationMs: 30000,
        sizeBytes: 1024,
        uploadState: 'pending'
      }]
    }))).toBeNull()

    expect(loadPendingMotionTrainingSession(memoryStorage({
      ...validBase,
      segments: [
        {
          index: 0,
          savedFilePath: 'wxfile://store/segment-0.mp4',
          durationMs: 30000,
          sizeBytes: 1024,
          uploadState: 'pending'
        },
        {
          index: 2,
          savedFilePath: 'wxfile://store/segment-2.mp4',
          durationMs: 30000,
          sizeBytes: 1024,
          uploadState: 'pending'
        }
      ]
    }))).toBeNull()
  })

  it('rejects finalized sessions that still have pending segments during cold recovery', () => {
    expect(loadPendingMotionTrainingSession(memoryStorage({
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      actionId: 42,
      trainingDate: '2026-07-11',
      expectedDurationSeconds: 180,
      actualDurationMs: 30000,
      finalized: true,
      createdAt: 1783692000000,
      segments: [{
        index: 0,
        savedFilePath: 'wxfile://store/segment-0.mp4',
        durationMs: 30000,
        sizeBytes: 1024,
        uploadState: 'pending'
      }]
    }))).toBeNull()
  })

  it('rejects sessions whose actual duration no longer matches the segment manifest', () => {
    expect(loadPendingMotionTrainingSession(memoryStorage({
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      actionId: 42,
      trainingDate: '2026-07-11',
      expectedDurationSeconds: 180,
      actualDurationMs: 29999,
      finalized: false,
      createdAt: 1783692000000,
      segments: [{
        index: 0,
        savedFilePath: 'wxfile://store/segment-0.mp4',
        durationMs: 30000,
        sizeBytes: 1024,
        uploadState: 'pending'
      }]
    }))).toBeNull()
  })

  it('restores finalized sessions with uploaded segments even when two sha256 values match', () => {
    expect(loadPendingMotionTrainingSession(memoryStorage({
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      actionId: 42,
      trainingDate: '2026-07-11',
      expectedDurationSeconds: 180,
      actualDurationMs: 60000,
      finalized: true,
      createdAt: 1783692000000,
      segments: [
        {
          index: 0,
          savedFilePath: 'wxfile://store/segment-0.mp4',
          durationMs: 30000,
          sizeBytes: 1024,
          uploadState: 'uploaded',
          sha256: 'same-sha'
        },
        {
          index: 1,
          savedFilePath: 'wxfile://store/segment-1.mp4',
          durationMs: 30000,
          sizeBytes: 1024,
          uploadState: 'uploaded',
          sha256: 'same-sha'
        }
      ]
    }))?.segments.map((segment) => segment.sha256)).toEqual(['same-sha', 'same-sha'])
  })

  it('validates the RFC4122 v4 client session id shape', () => {
    expect(() => createPendingMotionTrainingSession({
      actionId: 42,
      expectedDurationSeconds: 180,
      trainingDate: '2026-07-11',
      clientSessionId: 'not-a-v4-id',
      createdAt: 1783692000000
    })).toThrow('录像会话标识无效')
  })

  it('marks server-confirmed segment indexes without allowing premature local deletion', () => {
    const session = [
      { savedFilePath: 'wxfile://store/segment-0.mp4', durationSeconds: 30, sizeKb: 1000 },
      { savedFilePath: 'wxfile://store/segment-1.mp4', durationSeconds: 30, sizeKb: 1000 }
    ].reduce((current, segment) => appendPendingSegment(current, segment), createPendingMotionTrainingSession({
      actionId: 42,
      expectedDurationSeconds: 180,
      trainingDate: '2026-07-11',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: 1783692000000
    }))

    const recovered = markServerUploadedSegments(session, [0])

    expect(recovered.segments[0].uploadState).toBe('uploaded')
    expect(recovered.segments[0].sha256).toBeUndefined()
    expect(isSegmentReadyForLocalDeletion(recovered.segments[0])).toBe(false)
    expect(isSegmentReadyForLocalDeletion({
      ...recovered.segments[0],
      sha256: 'server-sha256'
    })).toBe(true)
  })

  it('clears pending session only through the named storage key', () => {
    const storage = memoryStorage()

    clearPendingMotionTrainingSession(storage)

    expect(storage.removeStorageSync).toHaveBeenCalledWith(PENDING_MOTION_TRAINING_SESSION_KEY)
  })

  it('migrates the old shoulder session without deleting it early', () => {
    const storage = memoryStorage()
    const pendingSession = createPendingMotionTrainingSession({
      actionId: 42,
      expectedDurationSeconds: 180,
      trainingDate: '2026-08-20',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: 1787193600000
    })
    storage.setStorageSync(LEGACY_PENDING_MOTION_TRAINING_SESSION_KEY, pendingSession)

    expect(loadPendingMotionTrainingSession(storage)).toMatchObject({ actionId: 42 })
    expect(storage.getStorageSync(PENDING_MOTION_TRAINING_SESSION_KEY)).toMatchObject({ actionId: 42 })
    expect(storage.getStorageSync(LEGACY_PENDING_MOTION_TRAINING_SESSION_KEY)).toMatchObject({ actionId: 42 })
  })

  it('clears both session keys after a completed or abandoned motion training session', () => {
    const storage = memoryStorage()

    clearPendingMotionTrainingSession(storage)

    expect(storage.removeStorageSync).toHaveBeenCalledWith(PENDING_MOTION_TRAINING_SESSION_KEY)
    expect(storage.removeStorageSync).toHaveBeenCalledWith(LEGACY_PENDING_MOTION_TRAINING_SESSION_KEY)
  })
})
