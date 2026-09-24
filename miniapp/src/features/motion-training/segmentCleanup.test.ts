import { describe, expect, it, vi } from 'vitest'
import { ABANDONED_MOTION_TRAINING_FILES_KEY, cleanupUploadedMotionTrainingSegments, retryAbandonedMotionTrainingFiles, rememberAbandonedMotionTrainingFiles } from './segmentCleanup'
import { createPendingMotionTrainingSession, loadPendingMotionTrainingSession, savePendingMotionTrainingSession, type PendingMotionTrainingSession } from './session'
import { pendingMotionTrainingLocalBytes } from './bufferGuard'

function fixture() {
  let stored: unknown
  const storage = { getStorageSync: () => stored, setStorageSync: (_key: string, value: unknown) => { stored = value } }
  const session: PendingMotionTrainingSession = {
    ...createPendingMotionTrainingSession({ actionId: 42, expectedDurationSeconds: 1800, trainingDate: '2026-09-24' }),
    actualDurationMs: 120000,
    segments: [0, 1].map(index => ({ index, compressionState: 'compressed', savedFilePath: `wxfile://temp/${index}.mp4`, durationMs: 60000, sizeBytes: 20, uploadState: index === 0 ? 'uploaded' : 'pending', localFileState: 'temporary' }))
  }
  savePendingMotionTrainingSession(storage, session)
  return {
    loadSession: () => loadPendingMotionTrainingSession(storage),
    saveSession: (next: PendingMotionTrainingSession) => savePendingMotionTrainingSession(storage, next)
  }
}

describe('segment cleanup acknowledgement', () => {
  it('preserves failed cleanup after completion and retries it before another recording', async () => {
    const entries = new Map<string, unknown>()
    const storage = { getStorageSync: (key: string) => entries.get(key), setStorageSync: (key: string, value: unknown) => { entries.set(key, value) }, removeStorageSync: (key: string) => { entries.delete(key) } }
    rememberAbandonedMotionTrainingFiles(storage, ['wxfile://temp/old.mp4'])
    rememberAbandonedMotionTrainingFiles(storage, ['wxfile://temp/new.mp4'])
    const releaseFile = vi.fn().mockResolvedValueOnce(false).mockResolvedValue(true)
    expect(await retryAbandonedMotionTrainingFiles(storage, releaseFile, () => true, new Set(['wxfile://temp/new.mp4']))).toBe(false)
    expect(releaseFile).toHaveBeenCalledTimes(1)
    expect(entries.get(ABANDONED_MOTION_TRAINING_FILES_KEY)).toMatchObject({ paths: ['wxfile://temp/old.mp4', 'wxfile://temp/new.mp4'] })
    expect(await retryAbandonedMotionTrainingFiles(storage, releaseFile, () => true, new Set())).toBe(true)
    expect(entries.has(ABANDONED_MOTION_TRAINING_FILES_KEY)).toBe(false)
  })
  it('does not undo uploaded acknowledgement if persisting cleanup completion fails', async () => {
    const store = fixture()
    await expect(cleanupUploadedMotionTrainingSegments({ ...store, saveSession: () => { throw new Error('storage full') }, releaseFile: async () => true })).resolves.toBeUndefined()
    expect(store.loadSession()!.segments[0]).toMatchObject({ uploadState: 'uploaded' })
    expect(pendingMotionTrainingLocalBytes(store.loadSession()!.segments)).toBe(40)
  })
  it('retains failed deletion across reload, retries only acknowledged files, and persists release', async () => {
    const store = fixture()
    const releaseFile = vi.fn().mockResolvedValueOnce(false).mockResolvedValue(true)
    await cleanupUploadedMotionTrainingSegments({ ...store, releaseFile })
    expect(pendingMotionTrainingLocalBytes(store.loadSession()!.segments)).toBe(40)
    await cleanupUploadedMotionTrainingSegments({ ...store, releaseFile })
    expect(pendingMotionTrainingLocalBytes(store.loadSession()!.segments)).toBe(20)
    await cleanupUploadedMotionTrainingSegments({ ...store, releaseFile })
    expect(releaseFile.mock.calls.map(([segment]) => segment.index)).toEqual([0, 0])
    expect(store.loadSession()!.segments[0]).toMatchObject({ uploadState: 'uploaded', localFileDeleted: true })
  })

  it('merges an asynchronous cleanup result into the latest manifest without losing newly recorded files', async () => {
    const store = fixture()
    await cleanupUploadedMotionTrainingSegments({ ...store, releaseFile: async () => {
      const latest = store.loadSession()!
      store.saveSession({ ...latest, actualDurationMs: 180000, segments: [...latest.segments, { ...latest.segments[1], index: 2 }] })
      return true
    } })
    expect(store.loadSession()!.segments).toHaveLength(3)
    expect(pendingMotionTrainingLocalBytes(store.loadSession()!.segments)).toBe(40)
  })

  it('does not write a late cleanup result into a replacement session', async () => {
    const store = fixture()
    await cleanupUploadedMotionTrainingSegments({ ...store, releaseFile: async () => {
      store.saveSession({ ...store.loadSession()!, clientSessionId: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee' })
      return true
    } })
    expect(pendingMotionTrainingLocalBytes(store.loadSession()!.segments)).toBe(40)
  })
})
