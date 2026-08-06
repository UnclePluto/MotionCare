import { describe, expect, it, vi } from 'vitest'

import {
  PENDING_SHOULDER_PRESS_SESSION_KEY,
  appendUploadableShoulderPressSegment,
  appendPendingSegment,
  buildShoulderPressCameraUrl,
  buildShoulderPressSessionUrl,
  buildShoulderPressUploadUrl,
  clearPendingShoulderPressSession,
  clientTrainingMoment,
  createPendingShoulderPressSession,
  isCompressedShoulderPressSegment,
  isSegmentReadyForLocalDeletion,
  loadPendingShoulderPressSession,
  markServerUploadedSegments,
  markShoulderPressTrainingEnded,
  markShoulderPressTrainingStarted,
  promoteLegacyShoulderPressSegment,
  savePendingShoulderPressSession
} from './session'

function memoryStorage(initial?: unknown) {
  const store = new Map<string, unknown>()
  if (initial !== undefined) store.set(PENDING_SHOULDER_PRESS_SESSION_KEY, initial)
  return {
    getStorageSync: vi.fn((key: string) => store.get(key)),
    setStorageSync: vi.fn((key: string, value: unknown) => store.set(key, value)),
    removeStorageSync: vi.fn((key: string) => store.delete(key))
  }
}

describe('shoulder press segmented session helpers', () => {
  it('builds session and upload urls', () => {
    expect(buildShoulderPressSessionUrl(42)).toBe('/pages/shoulder-press/index?actionId=42')
    expect(buildShoulderPressCameraUrl(42)).toBe('/pages/shoulder-press/camera?actionId=42')
    expect(buildShoulderPressUploadUrl()).toBe('/pages/shoulder-press/upload')
  })

  it('formats the phone instant with an explicit local offset', () => {
    expect(clientTrainingMoment(Date.UTC(2026, 7, 5, 16, 1, 2), 480)).toEqual({
      trainingDate: '2026-08-06',
      timestamp: '2026-08-06T00:01:02+08:00'
    })
  })

  it('sets the first start once and refreshes a stale pre-midnight training date', () => {
    const session = createPendingShoulderPressSession({
      actionId: 42,
      expectedDurationSeconds: 180,
      trainingDate: '2026-08-05',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: Date.UTC(2026, 7, 5, 15, 59, 0)
    })

    const started = markShoulderPressTrainingStarted(
      session,
      Date.UTC(2026, 7, 5, 16, 1, 2),
      480
    )
    const resumed = markShoulderPressTrainingStarted(
      started,
      Date.UTC(2026, 7, 5, 16, 5, 0),
      480
    )

    expect(started.trainingDate).toBe('2026-08-06')
    expect(started.trainingStartedAt).toBe('2026-08-06T00:01:02+08:00')
    expect(resumed.trainingStartedAt).toBe(started.trainingStartedAt)
  })

  it('sets the final end once and keeps it through storage recovery', () => {
    const started = markShoulderPressTrainingStarted(createPendingShoulderPressSession({
      actionId: 42,
      expectedDurationSeconds: 180,
      trainingDate: '2026-08-05',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: Date.UTC(2026, 7, 5, 15, 59, 0)
    }), Date.UTC(2026, 7, 5, 16, 1, 2), 480)
    const storage = memoryStorage()
    const ended = markShoulderPressTrainingEnded(started, Date.UTC(2026, 7, 5, 16, 9, 27), 480)

    savePendingShoulderPressSession(storage, ended)

    expect(loadPendingShoulderPressSession(storage)).toMatchObject({
      trainingStartedAt: '2026-08-06T00:01:02+08:00',
      trainingEndedAt: '2026-08-06T00:09:27+08:00'
    })
    expect(markShoulderPressTrainingEnded(
      ended,
      Date.UTC(2026, 7, 5, 16, 10, 0),
      480
    ).trainingEndedAt).toBe('2026-08-06T00:09:27+08:00')
  })

  it('rejects ending without a start and rejects a non-increasing end', () => {
    const session = createPendingShoulderPressSession({
      actionId: 42,
      expectedDurationSeconds: 180,
      trainingDate: '2026-08-06',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: Date.UTC(2026, 7, 5, 16, 0, 0)
    })

    expect(() => markShoulderPressTrainingEnded(
      session,
      Date.UTC(2026, 7, 5, 16, 9, 27),
      480
    )).toThrow('训练开始时间缺失')
    expect(() => markShoulderPressTrainingEnded({
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

    expect(loadPendingShoulderPressSession(memoryStorage(legacyManifest))).not.toBeNull()
    expect(loadPendingShoulderPressSession(memoryStorage({
      ...legacyManifest,
      trainingStartedAt: '2026-08-06T00:01:02'
    }))).toBeNull()
  })

  it('persists multiple saved segments and converts getVideoInfo kB to bytes', () => {
    const session = createPendingShoulderPressSession({
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
    const session = createPendingShoulderPressSession({
      actionId: 42,
      expectedDurationSeconds: 180,
      trainingDate: '2026-07-11',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: 1783692000000
    })

    const updated = appendUploadableShoulderPressSegment(session, {
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

  it('allows 2400 seconds and rejects a manifest duration above 2400000ms', () => {
    const session = createPendingShoulderPressSession({
      actionId: 42,
      expectedDurationSeconds: 2400,
      trainingDate: '2026-07-11',
      clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
      createdAt: 1783692000000
    })

    const full = appendUploadableShoulderPressSegment(session, {
      filePath: 'wxfile://temp/raw-0.mp4',
      durationMs: 2_400_000,
      sizeBytes: 1,
      localFileState: 'temporary'
    })

    expect(full.actualDurationMs).toBe(2_400_000)
    expect(() => appendUploadableShoulderPressSegment(session, {
      filePath: 'wxfile://temp/raw-1.mp4',
      durationMs: 2_400_001,
      sizeBytes: 1,
      localFileState: 'temporary'
    })).toThrow('录像总时长超过限制')
  })

  it('promotes a legacy pending-compression segment without changing its index', () => {
    const base = createPendingShoulderPressSession({
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

    const completed = promoteLegacyShoulderPressSegment(pending, 0, {
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
    expect(isCompressedShoulderPressSegment(completed.segments[0])).toBe(true)
  })

  it('loads the raw path and error from a legacy compression-failed manifest', () => {
    const restored = loadPendingShoulderPressSession(memoryStorage({
      ...createPendingShoulderPressSession({
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
    expect(restored && isCompressedShoulderPressSegment(restored.segments[0])).toBe(false)
  })

  it('loads old manifests without compressionState as compressed segments', () => {
    const restored = loadPendingShoulderPressSession(memoryStorage({
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
    const session = appendPendingSegment(createPendingShoulderPressSession({
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

    savePendingShoulderPressSession(storage, session)

    expect(loadPendingShoulderPressSession(storage)?.trainingDate).toBe('2026-07-11')
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

    expect(loadPendingShoulderPressSession(memoryStorage({
      ...validBase,
      segments: [{
        index: 0,
        savedFilePath: '',
        durationMs: 30000,
        sizeBytes: 1024,
        uploadState: 'pending'
      }]
    }))).toBeNull()

    expect(loadPendingShoulderPressSession(memoryStorage({
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
    expect(loadPendingShoulderPressSession(memoryStorage({
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
    expect(loadPendingShoulderPressSession(memoryStorage({
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
    expect(loadPendingShoulderPressSession(memoryStorage({
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
    expect(() => createPendingShoulderPressSession({
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
    ].reduce((current, segment) => appendPendingSegment(current, segment), createPendingShoulderPressSession({
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

    clearPendingShoulderPressSession(storage)

    expect(storage.removeStorageSync).toHaveBeenCalledWith(PENDING_SHOULDER_PRESS_SESSION_KEY)
  })
})
