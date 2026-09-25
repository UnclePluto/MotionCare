import { isCompressedMotionTrainingSegment, isUsableTempVideoPath, type CompressedMotionTrainingSegment, type PendingMotionTrainingSession, type StorageLike } from './session'

export const ABANDONED_MOTION_TRAINING_FILES_KEY = 'motioncare.motionTraining.abandonedFiles.v1'

function abandonedPaths(storage: StorageLike): string[] {
  const value = storage.getStorageSync(ABANDONED_MOTION_TRAINING_FILES_KEY) as { paths?: unknown } | undefined
  return Array.isArray(value?.paths) ? value.paths.filter(isUsableTempVideoPath) : []
}
export const hasAbandonedMotionTrainingFiles = (storage: StorageLike) => abandonedPaths(storage).length > 0

export function rememberAbandonedMotionTrainingFiles(storage: StorageLike, paths: string[]): void {
  const remaining = [...new Set([...abandonedPaths(storage), ...paths])]
  if (remaining.length) storage.setStorageSync(ABANDONED_MOTION_TRAINING_FILES_KEY, { paths: remaining, recordedAt: Date.now() })
}

export async function retryAbandonedMotionTrainingFiles(
  storage: StorageLike,
  releaseFile: (path: string, checkpointMoved: (path: string) => void) => Promise<boolean>,
  isActive: () => boolean,
  protectedPaths: Set<string>
): Promise<boolean> {
  for (const path of abandonedPaths(storage)) {
    if (!isActive()) return false
    if (protectedPaths.has(path)) continue
    let removed = false
    let currentPath = path
    try { removed = await releaseFile(path, movedPath => {
      const remaining = [...new Set(abandonedPaths(storage).map(item => item === currentPath ? movedPath : item))]
      storage.setStorageSync(ABANDONED_MOTION_TRAINING_FILES_KEY, { paths: remaining, recordedAt: Date.now() })
      currentPath = movedPath
    }) } catch { /* Retain the last checkpoint for the next preflight. */ }
    if (!isActive()) return false
    if (!removed) continue
    // A concurrent completion may have added other paths while deletion was pending.
    const remaining = abandonedPaths(storage).filter(item => item !== currentPath)
    if (remaining.length) storage.setStorageSync(ABANDONED_MOTION_TRAINING_FILES_KEY, { paths: remaining, recordedAt: Date.now() })
    else storage.removeStorageSync(ABANDONED_MOTION_TRAINING_FILES_KEY)
  }
  return abandonedPaths(storage).length === 0
}

/** Retry acknowledged files only. Reload around I/O so newly recorded segments are never overwritten. */
export async function cleanupUploadedMotionTrainingSegments(input: {
  loadSession: () => PendingMotionTrainingSession | null
  saveSession: (session: PendingMotionTrainingSession) => unknown
  releaseFile: (segment: CompressedMotionTrainingSegment) => Promise<boolean | { removed: boolean; filePath: string }>
}): Promise<void> {
  const initial = input.loadSession()
  if (!initial) return
  for (const candidate of initial.segments) {
    let latest = input.loadSession()
    if (!latest || latest.clientSessionId !== initial.clientSessionId) return
    const segment = latest.segments[candidate.index]
    if (!segment || !isCompressedMotionTrainingSegment(segment) || segment.uploadState !== 'uploaded' || segment.localFileDeleted) continue
    let removed = false
    let cleanedPath = segment.savedFilePath
    try {
      const result = await input.releaseFile(segment)
      removed = typeof result === 'boolean' ? result : result.removed
      if (typeof result !== 'boolean') cleanedPath = result.filePath
    } catch { /* Keep the path and occupied bytes for retry. */ }
    if (!removed) continue
    latest = input.loadSession()
    if (!latest || latest.clientSessionId !== initial.clientSessionId) return
    try {
      input.saveSession({ ...latest, segments: latest.segments.map(current => (
        current.index === segment.index && isCompressedMotionTrainingSegment(current) &&
        current.uploadState === 'uploaded' && current.savedFilePath === cleanedPath
          ? { ...current, localFileDeleted: true }
          : current
      )) })
    } catch {
      // The upload acknowledgement was saved before deletion. A failed cleanup
      // checkpoint must never send that segment back through the upload failure path.
      return
    }
  }
}
