import type { GameTrainingPayload } from './gameTypes'

export const PENDING_GAME_UPLOAD_KEY = 'motioncare.pendingGameUpload'
export const RETRY_DELAYS_SECONDS = [5, 10, 20, 40, 80, 160, 300, 300, 300, 300] as const
export const MAX_RETRY_PER_LAUNCH = 10

export type StorageLike = {
  getStorageSync(key: string): unknown
  setStorageSync(key: string, value: unknown): void
  removeStorageSync(key: string): void
}

export type PendingGameUpload = {
  payload: GameTrainingPayload
  retry_count: number
  total_retry_count: number
  next_retry_at: number
  last_error: string
  created_at: number
  retry_paused_until_next_launch: boolean
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value) && value >= 0
}

function hasGameTrainingRawDetail(value: unknown): value is GameTrainingPayload {
  return isRecord(value) && isRecord(value.form_data) && isRecord(value.form_data.raw_detail)
}

function isPendingGameUpload(value: unknown): value is PendingGameUpload {
  return (
    isRecord(value) &&
    hasGameTrainingRawDetail(value.payload) &&
    isNonNegativeInteger(value.retry_count) &&
    isNonNegativeInteger(value.total_retry_count) &&
    isNonNegativeInteger(value.next_retry_at) &&
    typeof value.last_error === 'string' &&
    isNonNegativeInteger(value.created_at) &&
    typeof value.retry_paused_until_next_launch === 'boolean'
  )
}

export function loadPendingGameUpload(storage: StorageLike): PendingGameUpload | null {
  try {
    const value = storage.getStorageSync(PENDING_GAME_UPLOAD_KEY)
    return isPendingGameUpload(value) ? value : null
  } catch {
    return null
  }
}

export function savePendingGameUpload(storage: StorageLike, payload: GameTrainingPayload, now: number): PendingGameUpload {
  const existing = loadPendingGameUpload(storage)
  if (existing) return existing

  const pending: PendingGameUpload = {
    payload,
    retry_count: 0,
    total_retry_count: 0,
    next_retry_at: now,
    last_error: '',
    created_at: now,
    retry_paused_until_next_launch: false,
  }
  storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, pending)
  return pending
}

export function clearPendingGameUpload(storage: StorageLike): void {
  storage.removeStorageSync(PENDING_GAME_UPLOAD_KEY)
}

export function markRetryFailure(storage: StorageLike, error: string, now: number): PendingGameUpload | null {
  const pending = loadPendingGameUpload(storage)
  if (!pending) return null
  if (pending.retry_paused_until_next_launch) return pending

  const retryCount = Math.min(MAX_RETRY_PER_LAUNCH, pending.retry_count + 1)
  const delayIndex = Math.min(retryCount - 1, RETRY_DELAYS_SECONDS.length - 1)
  const updated: PendingGameUpload = {
    ...pending,
    retry_count: retryCount,
    total_retry_count: pending.total_retry_count + 1,
    next_retry_at: now + RETRY_DELAYS_SECONDS[delayIndex] * 1000,
    last_error: error,
    retry_paused_until_next_launch: retryCount >= MAX_RETRY_PER_LAUNCH,
  }
  storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, updated)
  return updated
}

export function resetRetryWindowForLaunch(storage: StorageLike): PendingGameUpload | null {
  const pending = loadPendingGameUpload(storage)
  if (!pending) return null
  if (!pending.retry_paused_until_next_launch) return pending

  const updated: PendingGameUpload = {
    ...pending,
    retry_count: 0,
    next_retry_at: Date.now(),
    retry_paused_until_next_launch: false,
  }
  storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, updated)
  return updated
}
