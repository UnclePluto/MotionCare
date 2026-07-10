import { describe, expect, it, vi } from 'vitest'

import {
  PENDING_SHOULDER_PRESS_SESSION_KEY,
  appendPendingSegment,
  buildShoulderPressSessionUrl,
  buildShoulderPressUploadUrl,
  clearPendingShoulderPressSession,
  createPendingShoulderPressSession,
  isSegmentReadyForLocalDeletion,
  loadPendingShoulderPressSession,
  markServerUploadedSegments,
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
    expect(buildShoulderPressUploadUrl()).toBe('/pages/shoulder-press/upload')
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
      durationMs: 29800,
      sizeBytes: 2097152,
      uploadState: 'pending'
    })
    expect(updated.actualDurationMs).toBe(29800)
    expect(updated.trainingDate).toBe('2026-07-11')
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
