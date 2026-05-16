import Taro from '@tarojs/taro'

import { clearPatientAppToken, getPatientAppToken } from '../../auth/token'
import type { GameTrainingPayload } from './gameTypes'

export const PENDING_GAME_UPLOAD_KEY = 'motioncare.pendingGameUpload'
export const RETRY_DELAYS_SECONDS = [5, 10, 20, 40, 80, 160, 300, 300, 300, 300] as const
export const MAX_RETRY_PER_LAUNCH = 10

const API_BASE_URL = process.env.TARO_APP_API_BASE_URL || 'http://127.0.0.1:8000/api'
const RETRYABLE_STATUS_CODE_MIN = 500

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

export type TrainingRecordUploadError = Error & {
  retryable: boolean
  statusCode?: number
}

export type GameRecordUploader = (payload: GameTrainingPayload) => Promise<void>
export type PendingGameUploadRetryResult = 'none' | 'waiting' | 'uploaded' | 'failed' | 'rejected'
export type PendingGameUploadRetryLoopListener = (result: PendingGameUploadRetryResult) => void
export type PendingGameUploadRetryLoopOptions = {
  uploader?: GameRecordUploader
  now?: () => number
  onResult?: PendingGameUploadRetryLoopListener
}

let pendingRetryPromise: Promise<PendingGameUploadRetryResult> | null = null
let pendingRetryLoopTimer: ReturnType<typeof setTimeout> | null = null
let pendingRetryLoopActive = false
const pendingRetryLoopListeners = new Set<PendingGameUploadRetryLoopListener>()

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value) && value >= 0
}

function hasGameTrainingRawDetail(value: unknown): value is GameTrainingPayload {
  return isRecord(value) && isRecord(value.form_data) && isRecord(value.form_data.raw_detail)
}

function resolveErrorMessage(data: unknown): string {
  if (data && typeof data === 'object') {
    const detail = (data as { detail?: unknown }).detail
    const message = (data as { message?: unknown }).message
    if (typeof detail === 'string') return detail
    if (typeof message === 'string') return message
  }
  return '请求失败'
}

function createUploadError(message: string, retryable: boolean, statusCode?: number): TrainingRecordUploadError {
  const error = new Error(message) as TrainingRecordUploadError
  error.retryable = retryable
  if (statusCode !== undefined) {
    error.statusCode = statusCode
  }
  return error
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

export async function savePendingGameUploadAfterActiveRetry(
  storage: StorageLike,
  payload: GameTrainingPayload,
  now = Date.now()
): Promise<PendingGameUpload> {
  const existing = loadPendingGameUpload(storage)
  if (!existing) return savePendingGameUpload(storage, payload, now)
  if (!pendingRetryPromise) return existing

  await pendingRetryPromise
  const afterRetry = loadPendingGameUpload(storage)
  if (afterRetry) return afterRetry
  return savePendingGameUpload(storage, payload, Date.now())
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

export async function postGameTrainingRecord(payload: GameTrainingPayload): Promise<void> {
  const token = getPatientAppToken()
  let response: Taro.request.SuccessCallbackResult<Record<string, unknown>>
  try {
    response = await Taro.request<Record<string, unknown>>({
      url: `${API_BASE_URL}/patient-app/training-records/`,
      method: 'POST',
      data: payload,
      header: {
        'content-type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
  } catch (err) {
    throw createUploadError(err instanceof Error ? err.message : '网络异常，稍后自动补传', true)
  }

  const statusCode = Number(response.statusCode)
  if (!Number.isFinite(statusCode)) {
    throw createUploadError('网络异常，稍后自动补传', true)
  }
  if (statusCode >= 200 && statusCode < 300) return
  if (statusCode === 401 || statusCode === 403) {
    clearPatientAppToken()
    Taro.redirectTo({ url: '/pages/bind/index' })
    throw createUploadError('登录已失效', false, statusCode)
  }

  throw createUploadError(resolveErrorMessage(response.data), statusCode <= 0 || statusCode >= RETRYABLE_STATUS_CODE_MIN, statusCode)
}

function payloadForRetry(pending: PendingGameUpload): GameTrainingPayload {
  return {
    ...pending.payload,
    form_data: {
      ...pending.payload.form_data,
      raw_detail: {
        ...pending.payload.form_data.raw_detail,
        upload_mode: 'retry',
        retry_count: pending.retry_count,
        total_retry_count: pending.total_retry_count,
      },
    },
  }
}

function retryableFromUploadError(err: unknown): boolean {
  if (isRecord(err) && typeof err.retryable === 'boolean') {
    return err.retryable
  }
  if (isRecord(err) && typeof err.statusCode === 'number' && Number.isFinite(err.statusCode)) {
    return err.statusCode <= 0 || err.statusCode >= RETRYABLE_STATUS_CODE_MIN
  }
  return true
}

function messageFromUploadError(err: unknown): string {
  return err instanceof Error ? err.message : '上传失败，稍后自动补传'
}

export async function tryUploadPendingGameRecord(
  storage: StorageLike,
  now = Date.now(),
  uploader: GameRecordUploader = postGameTrainingRecord
): Promise<PendingGameUploadRetryResult> {
  if (pendingRetryPromise) return pendingRetryPromise

  const runRetry = async (): Promise<PendingGameUploadRetryResult> => {
    const pending = loadPendingGameUpload(storage)
    if (!pending) return 'none'
    if (pending.retry_paused_until_next_launch || pending.next_retry_at > now) return 'waiting'

    try {
      await uploader(payloadForRetry(pending))
    } catch (err) {
      if (!retryableFromUploadError(err)) {
        clearPendingGameUpload(storage)
        return 'rejected'
      }
      markRetryFailure(storage, messageFromUploadError(err), Date.now())
      return 'failed'
    }

    try {
      clearPendingGameUpload(storage)
    } catch {
      return 'rejected'
    }
    return 'uploaded'
  }

  pendingRetryPromise = runRetry().finally(() => {
    pendingRetryPromise = null
  })
  return pendingRetryPromise
}

export function stopPendingGameUploadRetryLoop(): void {
  pendingRetryLoopActive = false
  if (pendingRetryLoopTimer) {
    clearTimeout(pendingRetryLoopTimer)
    pendingRetryLoopTimer = null
  }
}

export function subscribePendingGameUploadRetryLoop(listener: PendingGameUploadRetryLoopListener): () => void {
  pendingRetryLoopListeners.add(listener)
  return () => {
    pendingRetryLoopListeners.delete(listener)
  }
}

function notifyPendingGameUploadRetryLoop(result: PendingGameUploadRetryResult): void {
  pendingRetryLoopListeners.forEach((listener) => {
    try {
      listener(result)
    } catch {
      // Keep the retry loop alive even if a page-level refresh callback fails.
    }
  })
}

export function startPendingGameUploadRetryLoop(
  storage: StorageLike,
  options: PendingGameUploadRetryLoopOptions = {}
): void {
  if (options.onResult) {
    pendingRetryLoopListeners.add(options.onResult)
  }
  if (pendingRetryLoopActive) return

  pendingRetryLoopActive = true
  const now = options.now ?? Date.now
  const uploader = options.uploader ?? postGameTrainingRecord

  const scheduleFromPending = () => {
    if (!pendingRetryLoopActive) return
    const pending = loadPendingGameUpload(storage)
    if (!pending || pending.retry_paused_until_next_launch) {
      stopPendingGameUploadRetryLoop()
      return
    }

    const delayMs = Math.max(0, pending.next_retry_at - now())
    if (pendingRetryLoopTimer) {
      clearTimeout(pendingRetryLoopTimer)
    }
    pendingRetryLoopTimer = setTimeout(runRetry, delayMs)
  }

  const handleRetryResult = (result: PendingGameUploadRetryResult) => {
    if (!pendingRetryLoopActive) return
    notifyPendingGameUploadRetryLoop(result)
    if (result === 'uploaded' || result === 'none' || result === 'rejected') {
      stopPendingGameUploadRetryLoop()
      return
    }
    scheduleFromPending()
  }

  const runRetry = () => {
    if (!pendingRetryLoopActive) return
    pendingRetryLoopTimer = null
    void tryUploadPendingGameRecord(storage, now(), uploader)
      .then(handleRetryResult)
      .catch(() => {
        stopPendingGameUploadRetryLoop()
      })
  }

  scheduleFromPending()
}
