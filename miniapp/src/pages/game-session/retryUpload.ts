import Taro from '@tarojs/taro'

import { resolveApiBaseUrl } from '../../api/baseUrl'
import { containsSensitiveCredentialText } from '../../api/safeError'
import { clearPatientAppToken, getPatientAppToken } from '../../auth/token'
import { neutralizeMiniappMessage } from '../../copy/neutralTerminology'
import type { GameTrainingPayload } from './gameTypes'

export const PENDING_GAME_UPLOAD_KEY = 'motioncare.pendingGameUpload'
export const RETRY_DELAYS_SECONDS = [5, 10, 20, 40, 80, 160, 300, 300, 300, 300] as const
export const MAX_RETRY_PER_LAUNCH = 10

const API_BASE_URL = process.env.TARO_APP_API_BASE_URL || 'http://127.0.0.1:8000/api'
const RETRYABLE_STATUS_CODE_MIN = 500

function runtimeApiBaseUrl(): string {
  try {
    return resolveApiBaseUrl(API_BASE_URL, Taro.getDeviceInfo().platform)
  } catch {
    return API_BASE_URL
  }
}

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

type PendingRetryOutcome = { result: PendingGameUploadRetryResult; stopLoop: boolean }
let pendingRetryPromise: Promise<PendingRetryOutcome> | null = null
let pendingRetryLoopTimer: ReturnType<typeof setTimeout> | null = null
let pendingRetryLoopActive = false
const pendingRetryLoopListeners = new Set<PendingGameUploadRetryLoopListener>()

function copyStoredValue<T>(value: T): T {
  if (Array.isArray(value)) return value.map(item => copyStoredValue(item)) as T
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, copyStoredValue(item)])) as T
  }
  return value
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

function safeGameUploadErrorMessage(message: string, sensitiveFallback: string): string {
  if (containsSensitiveCredentialText(message)) {
    return neutralizeMiniappMessage(sensitiveFallback)
  }
  return neutralizeMiniappMessage(message)
}

function resolveErrorMessage(data: unknown): string {
  if (data && typeof data === 'object') {
    const detail = (data as { detail?: unknown }).detail
    const message = (data as { message?: unknown }).message
    if (typeof detail === 'string') return safeGameUploadErrorMessage(detail, '请求失败')
    if (typeof message === 'string') return safeGameUploadErrorMessage(message, '请求失败')
  }
  return neutralizeMiniappMessage('请求失败')
}

function createUploadError(
  message: string,
  retryable: boolean,
  statusCode?: number,
  sensitiveFallback = '上传失败，稍后自动补传'
): TrainingRecordUploadError {
  const error = new Error(safeGameUploadErrorMessage(message, sensitiveFallback)) as TrainingRecordUploadError
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

// 单条仍写旧对象格式；多条写同一key下的数组，一次同步写入避免双key迁移丢失。
function readPendingQueue(storage: StorageLike): PendingGameUpload[] {
  const value = storage.getStorageSync(PENDING_GAME_UPLOAD_KEY)
  if (isPendingGameUpload(value)) return [copyStoredValue(value)]
  if (Array.isArray(value) && value.every(isPendingGameUpload)) return copyStoredValue(value)
  return []
}

function writePendingQueue(storage: StorageLike, queue: PendingGameUpload[]): void {
  if (queue.length === 0) storage.removeStorageSync(PENDING_GAME_UPLOAD_KEY)
  else storage.setStorageSync(PENDING_GAME_UPLOAD_KEY, copyStoredValue(queue.length === 1 ? queue[0] : queue))
}

function sameSession(left: GameTrainingPayload, right: GameTrainingPayload): boolean {
  if (left.client_session_id || right.client_session_id) return left.client_session_id === right.client_session_id
  // 旧缓存没有UUID，完整原始载荷作为本地身份，不给旧载荷补字段。
  return JSON.stringify(left) === JSON.stringify(right)
}

export function loadPendingGameUpload(storage: StorageLike): PendingGameUpload | null {
  try { return readPendingQueue(storage)[0] ?? null } catch { return null }
}

export function savePendingGameUpload(storage: StorageLike, payload: GameTrainingPayload, now: number): PendingGameUpload {
  const queue = readPendingQueue(storage)
  const existing = queue.find(item => sameSession(item.payload, payload))
  if (existing) return existing
  const pending: PendingGameUpload = {
    payload: copyStoredValue(payload),
    retry_count: 0,
    total_retry_count: 0,
    next_retry_at: now,
    last_error: '',
    created_at: now,
    retry_paused_until_next_launch: false,
  }
  writePendingQueue(storage, [...queue, pending])
  return pending
}

export async function savePendingGameUploadAfterActiveRetry(
  storage: StorageLike,
  payload: GameTrainingPayload,
  now = Date.now()
): Promise<PendingGameUpload> {
  // 立即入队，正在补传旧记录也不推迟新记录持久化。
  return savePendingGameUpload(storage, payload, now)
}

export function clearPendingGameUpload(storage: StorageLike, payload?: GameTrainingPayload): void {
  const queue = readPendingQueue(storage)
  const target = payload ?? queue[0]?.payload
  if (!target) return
  writePendingQueue(storage, queue.filter(item => !sameSession(item.payload, target)))
}

export function markRetryFailure(storage: StorageLike, error: string, now: number, payload?: GameTrainingPayload): PendingGameUpload | null {
  const queue = readPendingQueue(storage)
  const pending = payload ? queue.find(item => sameSession(item.payload, payload)) : queue[0]
  if (!pending) return null
  if (pending.retry_paused_until_next_launch) return pending
  const retryCount = Math.min(MAX_RETRY_PER_LAUNCH, pending.retry_count + 1)
  const delayIndex = Math.min(retryCount - 1, RETRY_DELAYS_SECONDS.length - 1)
  const updated: PendingGameUpload = {
    ...pending,
    retry_count: retryCount,
    total_retry_count: pending.total_retry_count + 1,
    next_retry_at: now + RETRY_DELAYS_SECONDS[delayIndex] * 1000,
    last_error: safeGameUploadErrorMessage(error, '上传失败，稍后自动补传'),
    retry_paused_until_next_launch: retryCount >= MAX_RETRY_PER_LAUNCH,
  }
  writePendingQueue(storage, queue.map(item => sameSession(item.payload, pending.payload) ? updated : item))
  return updated
}

export function resetRetryWindowForLaunch(storage: StorageLike): PendingGameUpload | null {
  const queue = readPendingQueue(storage)
  if (!queue.some(item => item.retry_paused_until_next_launch)) return queue[0] ?? null
  const updated = queue.map(item => item.retry_paused_until_next_launch ? {
    ...item, retry_count: 0, next_retry_at: Date.now(), retry_paused_until_next_launch: false,
  } : item)
  writePendingQueue(storage, updated)
  return updated[0] ?? null
}

export async function postGameTrainingRecord(payload: GameTrainingPayload): Promise<void> {
  const token = getPatientAppToken()
  let response: Taro.request.SuccessCallbackResult<Record<string, unknown>>
  try {
    response = await Taro.request<Record<string, unknown>>({
      url: `${runtimeApiBaseUrl()}/patient-app/training-records/`,
      method: 'POST',
      data: payload,
      header: {
        'content-type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
  } catch (err) {
    throw createUploadError(
      err instanceof Error ? err.message : '网络异常，稍后自动补传',
      true,
      undefined,
      '网络异常，稍后自动补传'
    )
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
  return safeGameUploadErrorMessage(
    err instanceof Error ? err.message : '上传失败，稍后自动补传',
    '上传失败，稍后自动补传'
  )
}

export async function tryUploadPendingGameRecord(
  storage: StorageLike,
  now = Date.now(),
  uploader: GameRecordUploader = postGameTrainingRecord
): Promise<PendingGameUploadRetryResult> {
  return (await retryPendingGameRecord(storage, now, uploader)).result
}

async function retryPendingGameRecord(
  storage: StorageLike,
  now = Date.now(),
  uploader: GameRecordUploader = postGameTrainingRecord
): Promise<PendingRetryOutcome> {
  if (pendingRetryPromise) return pendingRetryPromise

  const runRetry = async (): Promise<PendingRetryOutcome> => {
    const pending = loadPendingGameUpload(storage)
    if (!pending) return { result: 'none', stopLoop: true }
    if (pending.retry_paused_until_next_launch || pending.next_retry_at > now) return { result: 'waiting', stopLoop: false }

    try {
      await uploader(payloadForRetry(pending))
    } catch (err) {
      if (!retryableFromUploadError(err)) {
        clearPendingGameUpload(storage, pending.payload)
        return { result: 'rejected', stopLoop: isRecord(err) && (err.statusCode === 401 || err.statusCode === 403) }
      }
      markRetryFailure(storage, messageFromUploadError(err), Date.now(), pending.payload)
      return { result: 'failed', stopLoop: false }
    }

    try {
      clearPendingGameUpload(storage, pending.payload)
    } catch {
      return { result: 'rejected', stopLoop: true }
    }
    return { result: 'uploaded', stopLoop: false }
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

  const handleRetryResult = ({ result, stopLoop }: PendingRetryOutcome) => {
    if (!pendingRetryLoopActive) return
    notifyPendingGameUploadRetryLoop(result)
    if (stopLoop) {
      stopPendingGameUploadRetryLoop()
      return
    }
    scheduleFromPending()
  }

  const runRetry = () => {
    if (!pendingRetryLoopActive) return
    pendingRetryLoopTimer = null
    void retryPendingGameRecord(storage, now(), uploader)
      .then(handleRetryResult)
      .catch(() => {
        stopPendingGameUploadRetryLoop()
      })
  }

  scheduleFromPending()
}
