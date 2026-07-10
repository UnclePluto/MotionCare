export const SHOULDER_PRESS_SOURCE_KEY = 'motion-resistance-shoulder-press'
export const PENDING_SHOULDER_PRESS_UPLOAD_KEY = 'motioncare.pendingShoulderPressUpload'

export type PendingShoulderPressUpload = {
  actionId: number
  tempFilePath: string
  durationSeconds: number
  sizeBytes: number
  createdAt: number
  videoId?: number
  key?: string
  uploadToken?: string
  uploadHost?: string
  expiresAt?: number
  hash?: string
  lastError?: string
}

export type ShoulderPressUploadIntentState = Required<Pick<
  PendingShoulderPressUpload,
  'videoId' | 'key' | 'uploadToken' | 'uploadHost' | 'expiresAt'
>>

type StorageLike = {
  getStorageSync: (key: string) => unknown
  setStorageSync: (key: string, value: unknown) => void
  removeStorageSync: (key: string) => void
}

type VideoInfo = {
  duration: number
  size: number
}

function isPositiveNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
}

function isPositiveInteger(value: unknown): value is number {
  return isPositiveNumber(value) && Number.isInteger(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

export function isUsableTempVideoPath(value: unknown): value is string {
  if (!isNonEmptyString(value) || /\s/.test(value)) return false
  return /^(?:wxfile|https?|file):\/\//.test(value) || value.startsWith('blob:') || value.startsWith('/')
}

export function buildPendingShoulderPressUpload(input: {
  actionId: number
  tempFilePath: string
  videoInfo: VideoInfo
  createdAt?: number
}): PendingShoulderPressUpload {
  if (!isPositiveInteger(input.actionId)) throw new Error('训练动作无效')
  if (!isUsableTempVideoPath(input.tempFilePath)) throw new Error('录像文件路径无效')
  if (!isPositiveNumber(input.videoInfo.duration)) throw new Error('录像时长无效')
  if (!isPositiveNumber(input.videoInfo.size)) throw new Error('录像文件大小无效')

  const createdAt = input.createdAt ?? Date.now()
  if (!isPositiveNumber(createdAt)) throw new Error('录像创建时间无效')

  return {
    actionId: input.actionId,
    tempFilePath: input.tempFilePath,
    durationSeconds: Math.max(1, Math.round(input.videoInfo.duration)),
    sizeBytes: Math.max(1, Math.round(input.videoInfo.size)),
    createdAt
  }
}

export function buildShoulderPressSessionUrl(actionId: number): string {
  return `/pages/shoulder-press/index?actionId=${encodeURIComponent(String(actionId))}`
}

export function buildShoulderPressUploadUrl(): string {
  return '/pages/shoulder-press/upload'
}

export function hasShoulderPressUploadIntent(
  pending: PendingShoulderPressUpload
): pending is PendingShoulderPressUpload & ShoulderPressUploadIntentState {
  return isPositiveInteger(pending.videoId)
    && isNonEmptyString(pending.key)
    && isNonEmptyString(pending.uploadToken)
    && isNonEmptyString(pending.uploadHost)
    && isPositiveNumber(pending.expiresAt)
}

export function clearShoulderPressUploadIntent(
  pending: PendingShoulderPressUpload
): PendingShoulderPressUpload {
  const {
    videoId: _videoId,
    key: _key,
    uploadToken: _uploadToken,
    uploadHost: _uploadHost,
    expiresAt: _expiresAt,
    hash: _hash,
    ...base
  } = pending
  return base
}

export function savePendingShoulderPressUpload(
  storage: StorageLike,
  payload: PendingShoulderPressUpload
): void {
  storage.setStorageSync(PENDING_SHOULDER_PRESS_UPLOAD_KEY, payload)
}

export function loadPendingShoulderPressUpload(storage: StorageLike): PendingShoulderPressUpload | null {
  const value = storage.getStorageSync(PENDING_SHOULDER_PRESS_UPLOAD_KEY)
  if (!value || typeof value !== 'object') return null

  const pending = value as Partial<PendingShoulderPressUpload>
  if (!isPositiveInteger(pending.actionId)
    || !isUsableTempVideoPath(pending.tempFilePath)
    || !isPositiveInteger(pending.durationSeconds)
    || !isPositiveInteger(pending.sizeBytes)
    || !isPositiveNumber(pending.createdAt)) {
    return null
  }

  const base: PendingShoulderPressUpload = {
    actionId: pending.actionId,
    tempFilePath: pending.tempFilePath,
    durationSeconds: pending.durationSeconds,
    sizeBytes: pending.sizeBytes,
    createdAt: pending.createdAt,
    ...(typeof pending.lastError === 'string' ? { lastError: pending.lastError } : {})
  }
  const withIntent: PendingShoulderPressUpload = {
    ...base,
    videoId: pending.videoId,
    key: pending.key,
    uploadToken: pending.uploadToken,
    uploadHost: pending.uploadHost,
    expiresAt: pending.expiresAt
  }
  if (!hasShoulderPressUploadIntent(withIntent)) return base
  if (pending.hash !== undefined && !isNonEmptyString(pending.hash)) return base

  return pending.hash === undefined ? withIntent : { ...withIntent, hash: pending.hash }
}

export function clearPendingShoulderPressUpload(storage: StorageLike): void {
  storage.removeStorageSync(PENDING_SHOULDER_PRESS_UPLOAD_KEY)
}
