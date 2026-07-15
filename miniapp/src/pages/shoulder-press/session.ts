export const SHOULDER_PRESS_SOURCE_KEY = 'motion-resistance-shoulder-press'
export const PENDING_SHOULDER_PRESS_SESSION_KEY = 'motioncare.pendingShoulderPressSession'

export type ShoulderPressSegmentStatus = 'pending' | 'uploading' | 'retrying' | 'confirmed'

export type PendingShoulderPressSegment = {
  sequenceIndex: number
  savedFilePath: string
  durationSeconds: number
  sizeBytes: number
  status: ShoulderPressSegmentStatus
  retryCount: number
  nextRetryAt?: number
  lastError?: string
}

export type ShoulderPressSession = {
  actionId: number
  videoId: number
  startedAt: number
  durationSeconds: number
  phase: 'recording' | 'uploading' | 'processing'
  segmentCount?: number
  trainingDate?: string
  unrecoverableReason?: string
  segments: PendingShoulderPressSegment[]
}

export type StorageLike = {
  getStorageSync: (key: string) => unknown
  setStorageSync: (key: string, value: unknown) => void
  removeStorageSync?: (key: string) => void
}

export function buildShoulderPressSessionUrl(actionId: number): string {
  return `/pages/shoulder-press/index?actionId=${actionId}`
}

export function buildShoulderPressCameraUrl(actionId: number): string {
  return `/pages/shoulder-press/camera?actionId=${actionId}`
}

export function buildShoulderPressUploadUrl(): string {
  return '/pages/shoulder-press/upload'
}

export function saveShoulderPressSession(
  storage: StorageLike,
  session: ShoulderPressSession,
): void {
  storage.setStorageSync(PENDING_SHOULDER_PRESS_SESSION_KEY, session)
}

export function loadShoulderPressSession(storage: StorageLike): ShoulderPressSession | null {
  const value = storage.getStorageSync(PENDING_SHOULDER_PRESS_SESSION_KEY)
  if (!value || typeof value !== 'object') return null
  const session = value as Partial<ShoulderPressSession>
  if (
    typeof session.actionId !== 'number'
    || typeof session.videoId !== 'number'
    || typeof session.startedAt !== 'number'
    || typeof session.durationSeconds !== 'number'
    || !Array.isArray(session.segments)
    || !['recording', 'uploading', 'processing'].includes(session.phase || '')
  ) return null
  return session as ShoulderPressSession
}

export function clearShoulderPressSession(storage: StorageLike): void {
  storage.removeStorageSync?.(PENDING_SHOULDER_PRESS_SESSION_KEY)
}
