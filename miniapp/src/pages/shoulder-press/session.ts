export const SHOULDER_PRESS_SOURCE_KEY = 'motion-resistance-shoulder-press'
export const PENDING_SHOULDER_PRESS_SESSION_KEY = 'motioncare.pendingShoulderPressSession'
export const PENDING_SHOULDER_PRESS_UPLOAD_KEY = PENDING_SHOULDER_PRESS_SESSION_KEY

export type LegacyPendingCompressionShoulderPressSegment = {
  index: number
  compressionState: 'pending_compression' | 'compression_failed'
  rawSavedFilePath: string
  durationMs: number
  compressionError?: string
}

export type CompressedShoulderPressSegment = {
  index: number
  compressionState: 'compressed'
  savedFilePath: string
  durationMs: number
  sizeBytes: number
  uploadState: 'pending' | 'uploading' | 'uploaded'
  localFileState?: 'temporary' | 'save_failed' | 'saved'
  sha256?: string
}

export type PendingShoulderPressSegment =
  | LegacyPendingCompressionShoulderPressSegment
  | CompressedShoulderPressSegment

export type PendingShoulderPressSession = {
  clientSessionId: string
  videoId?: number
  actionId: number
  trainingDate: string
  trainingStartedAt?: string
  trainingEndedAt?: string
  expectedDurationSeconds: number
  actualDurationMs: number
  segments: PendingShoulderPressSegment[]
  finalized: boolean
  createdAt: number
  lastError?: string
}

export type PendingShoulderPressUpload = PendingShoulderPressSession & {
  tempFilePath?: string
  durationSeconds?: number
  sizeBytes?: number
  hash?: string
}

type StorageLike = {
  getStorageSync: (key: string) => unknown
  setStorageSync: (key: string, value: unknown) => void
  removeStorageSync: (key: string) => void
}

type VideoInfo = {
  duration: number
  size: number
}

const UUID_V4_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const OFFSET_ISO_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?(?:Z|[+-]\d{2}:\d{2})$/
const MAX_SHOULDER_PRESS_MANIFEST_DURATION_MS = 2_400_000

function twoDigits(value: number): string {
  return String(value).padStart(2, '0')
}

function isPositiveNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
}

function isNonNegativeNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
}

function isPositiveInteger(value: unknown): value is number {
  return isPositiveNumber(value) && Number.isInteger(value)
}

function isNonNegativeInteger(value: unknown): value is number {
  return isNonNegativeNumber(value) && Number.isInteger(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function isTrainingDate(value: unknown): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
}

function assertValidClientSessionId(value: string): void {
  if (!UUID_V4_PATTERN.test(value)) throw new Error('录像会话标识无效')
}

export function createClientSessionId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (marker) => {
    const value = marker === 'x' ? Math.floor(Math.random() * 16) : (Math.floor(Math.random() * 4) + 8)
    return value.toString(16)
  })
}

export function isUsableTempVideoPath(value: unknown): value is string {
  if (!isNonEmptyString(value) || /\s/.test(value)) return false
  return /^(?:wxfile|https?|file):\/\//.test(value) || value.startsWith('blob:') || value.startsWith('/')
}

export function buildShoulderPressSessionUrl(actionId: number): string {
  return `/pages/shoulder-press/index?actionId=${encodeURIComponent(String(actionId))}`
}

export function buildShoulderPressCameraUrl(actionId: number): string {
  return `/pages/shoulder-press/camera?actionId=${encodeURIComponent(String(actionId))}`
}

export function buildShoulderPressUploadUrl(): string {
  return '/pages/shoulder-press/upload'
}

export function normalizeShoulderPressExpectedDurationSeconds(value: number): number {
  if (!Number.isFinite(value)) return 1
  return Math.min(2400, Math.max(1, Math.round(value)))
}

export function clientTrainingMoment(
  nowMs: number,
  offsetMinutes = -new Date(nowMs).getTimezoneOffset()
): { trainingDate: string; timestamp: string } {
  const shifted = new Date(nowMs + offsetMinutes * 60_000)
  const trainingDate = [
    shifted.getUTCFullYear(),
    twoDigits(shifted.getUTCMonth() + 1),
    twoDigits(shifted.getUTCDate())
  ].join('-')
  const localTime = [
    twoDigits(shifted.getUTCHours()),
    twoDigits(shifted.getUTCMinutes()),
    twoDigits(shifted.getUTCSeconds())
  ].join(':')
  const sign = offsetMinutes >= 0 ? '+' : '-'
  const absoluteOffset = Math.abs(offsetMinutes)
  const offset = `${sign}${twoDigits(Math.floor(absoluteOffset / 60))}:${twoDigits(absoluteOffset % 60)}`
  return { trainingDate, timestamp: `${trainingDate}T${localTime}${offset}` }
}

export function createPendingShoulderPressSession(input: {
  actionId: number
  expectedDurationSeconds: number
  trainingDate: string
  clientSessionId?: string
  createdAt?: number
}): PendingShoulderPressSession {
  if (!isPositiveInteger(input.actionId)) throw new Error('训练动作无效')
  if (!isPositiveNumber(input.expectedDurationSeconds)) throw new Error('预计训练时长无效')
  if (!isTrainingDate(input.trainingDate)) throw new Error('训练日期无效')

  const clientSessionId = input.clientSessionId ?? createClientSessionId()
  assertValidClientSessionId(clientSessionId)
  const createdAt = input.createdAt ?? Date.now()
  if (!isPositiveNumber(createdAt)) throw new Error('录像创建时间无效')

  return {
    clientSessionId,
    actionId: input.actionId,
    trainingDate: input.trainingDate,
    expectedDurationSeconds: normalizeShoulderPressExpectedDurationSeconds(
      input.expectedDurationSeconds
    ),
    actualDurationMs: 0,
    segments: [],
    finalized: false,
    createdAt
  }
}

export function markShoulderPressTrainingStarted(
  session: PendingShoulderPressSession,
  nowMs: number,
  offsetMinutes?: number
): PendingShoulderPressSession {
  if (session.trainingStartedAt) return session
  const moment = clientTrainingMoment(nowMs, offsetMinutes)
  return {
    ...session,
    trainingDate: moment.trainingDate,
    trainingStartedAt: moment.timestamp
  }
}

export function requireShoulderPressTrainingStartedAt(
  session: PendingShoulderPressSession
): string {
  if (!session.trainingStartedAt) {
    throw new Error('训练开始时间缺失，请重新训练')
  }
  return session.trainingStartedAt
}

export function markShoulderPressTrainingEnded(
  session: PendingShoulderPressSession,
  nowMs: number,
  offsetMinutes?: number
): PendingShoulderPressSession {
  if (!session.trainingStartedAt) throw new Error('训练开始时间缺失，请重新训练')
  if (session.trainingEndedAt) return session
  const moment = clientTrainingMoment(nowMs, offsetMinutes)
  if (Date.parse(moment.timestamp) <= Date.parse(session.trainingStartedAt)) {
    throw new Error('训练结束时间必须晚于开始时间')
  }
  return { ...session, trainingEndedAt: moment.timestamp }
}

export function appendPendingSegment(
  session: PendingShoulderPressSession,
  input: {
    savedFilePath: string
    durationSeconds: number
    sizeKb: number
  }
): PendingShoulderPressSession {
  if (!isUsableTempVideoPath(input.savedFilePath)) throw new Error('录像文件路径无效')
  if (!isPositiveNumber(input.durationSeconds)) throw new Error('录像时长无效')
  if (!isPositiveNumber(input.sizeKb)) throw new Error('录像文件大小无效')

  const durationMs = Math.max(1, Math.round(input.durationSeconds * 1000))
  const sizeBytes = Math.max(1, Math.round(input.sizeKb * 1024))
  return appendUploadableShoulderPressSegment(session, {
    filePath: input.savedFilePath,
    durationMs,
    sizeBytes,
    localFileState: 'saved'
  })
}

export function appendUploadableShoulderPressSegment(
  session: PendingShoulderPressSession,
  input: {
    filePath: string
    durationMs: number
    sizeBytes: number
    localFileState: 'temporary' | 'save_failed' | 'saved'
  }
): PendingShoulderPressSession {
  if (!isUsableTempVideoPath(input.filePath)) throw new Error('录像文件路径无效')
  if (!isPositiveInteger(input.durationMs)) throw new Error('录像时长无效')
  if (!isPositiveInteger(input.sizeBytes)) throw new Error('录像文件大小无效')
  const durationMs = input.durationMs
  if (session.actualDurationMs + durationMs > MAX_SHOULDER_PRESS_MANIFEST_DURATION_MS) {
    throw new Error('录像总时长超过限制，请重新录制')
  }
  const segment: PendingShoulderPressSegment = {
    index: session.segments.length,
    compressionState: 'compressed',
    savedFilePath: input.filePath,
    durationMs,
    sizeBytes: input.sizeBytes,
    uploadState: 'pending',
    localFileState: input.localFileState
  }

  return {
    ...session,
    actualDurationMs: session.actualDurationMs + durationMs,
    segments: [...session.segments, segment],
    lastError: undefined
  }
}

export function isCompressedShoulderPressSegment(
  segment: PendingShoulderPressSegment
): segment is CompressedShoulderPressSegment {
  return segment.compressionState === 'compressed'
}

export function promoteLegacyShoulderPressSegment(
  session: PendingShoulderPressSession,
  index: number,
  input: {
    savedFilePath: string
    durationMs: number
    sizeBytes: number
    localFileState?: 'temporary' | 'save_failed' | 'saved'
  }
): PendingShoulderPressSession {
  if (!isUsableTempVideoPath(input.savedFilePath)) throw new Error('录像文件路径无效')
  if (!isPositiveInteger(input.durationMs)) throw new Error('录像时长无效')
  if (!isPositiveInteger(input.sizeBytes)) throw new Error('录像文件大小无效')
  const current = session.segments[index]
  if (!current || current.index !== index || isCompressedShoulderPressSegment(current)) {
    throw new Error('待上传录像分段不存在')
  }
  const actualDurationMs = session.actualDurationMs - current.durationMs + input.durationMs
  if (actualDurationMs > MAX_SHOULDER_PRESS_MANIFEST_DURATION_MS) {
    throw new Error('录像总时长超过限制，请重新录制')
  }

  return {
    ...session,
    actualDurationMs,
    segments: session.segments.map((segment) => (
      segment.index === index
        ? {
            index,
            compressionState: 'compressed',
            savedFilePath: input.savedFilePath,
            durationMs: input.durationMs,
            sizeBytes: input.sizeBytes,
            uploadState: 'pending',
            localFileState: input.localFileState ?? 'saved'
          }
        : segment
    )),
    lastError: undefined
  }
}

export function markServerUploadedSegments(
  session: PendingShoulderPressSession,
  uploadedIndexes: number[]
): PendingShoulderPressSession {
  const uploaded = new Set(uploadedIndexes.filter((index) => Number.isInteger(index) && index >= 0))
  return {
    ...session,
    segments: session.segments.map((segment) => (
      uploaded.has(segment.index) && isCompressedShoulderPressSegment(segment)
        ? { ...segment, uploadState: 'uploaded' }
        : segment
    ))
  }
}

export function isSegmentReadyForLocalDeletion(segment: PendingShoulderPressSegment): boolean {
  return (
    isCompressedShoulderPressSegment(segment) &&
    segment.uploadState === 'uploaded' &&
    isNonEmptyString(segment.sha256)
  )
}

function normalizeSegment(value: unknown, expectedIndex: number): PendingShoulderPressSegment | null {
  if (!value || typeof value !== 'object') return null
  const segment = value as Record<string, unknown>
  if (segment.index !== expectedIndex) return null
  if (!isPositiveInteger(segment.durationMs)) return null
  if (
    segment.compressionState === 'pending_compression' ||
    segment.compressionState === 'compression_failed'
  ) {
    if (!isUsableTempVideoPath(segment.rawSavedFilePath)) return null
    if (
      segment.compressionState === 'compression_failed' &&
      !isNonEmptyString(segment.compressionError)
    ) return null
    return {
      index: expectedIndex,
      compressionState: segment.compressionState,
      rawSavedFilePath: segment.rawSavedFilePath,
      durationMs: segment.durationMs,
      ...(isNonEmptyString(segment.compressionError)
        ? { compressionError: segment.compressionError }
        : {})
    }
  }

  if (segment.compressionState !== undefined && segment.compressionState !== 'compressed') return null
  if (!isUsableTempVideoPath(segment.savedFilePath)) return null
  if (!isPositiveInteger(segment.sizeBytes)) return null
  if (segment.uploadState !== 'pending' && segment.uploadState !== 'uploading' && segment.uploadState !== 'uploaded') {
    return null
  }
  if (segment.sha256 !== undefined && !isNonEmptyString(segment.sha256)) return null
  if (
    segment.localFileState !== undefined &&
    segment.localFileState !== 'temporary' &&
    segment.localFileState !== 'save_failed' &&
    segment.localFileState !== 'saved'
  ) return null

  return {
    index: expectedIndex,
    compressionState: 'compressed',
    savedFilePath: segment.savedFilePath,
    durationMs: segment.durationMs,
    sizeBytes: segment.sizeBytes,
    uploadState: segment.uploadState,
    localFileState: segment.localFileState ?? 'saved',
    ...(segment.sha256 ? { sha256: segment.sha256 } : {})
  }
}

function normalizeSession(value: unknown): PendingShoulderPressSession | null {
  if (!value || typeof value !== 'object') return null
  const session = value as Partial<PendingShoulderPressSession>
  if (!isNonEmptyString(session.clientSessionId) || !UUID_V4_PATTERN.test(session.clientSessionId)) return null
  if (!isPositiveInteger(session.actionId)) return null
  if (!isTrainingDate(session.trainingDate)) return null
  if (!isPositiveNumber(session.expectedDurationSeconds)) return null
  if (!isNonNegativeInteger(session.actualDurationMs)) return null
  if (!Array.isArray(session.segments)) return null
  if (typeof session.finalized !== 'boolean') return null
  if (!isPositiveNumber(session.createdAt)) return null
  if (
    session.trainingStartedAt !== undefined &&
    (!isNonEmptyString(session.trainingStartedAt) || !OFFSET_ISO_PATTERN.test(session.trainingStartedAt))
  ) return null
  if (
    session.trainingEndedAt !== undefined &&
    (!isNonEmptyString(session.trainingEndedAt) || !OFFSET_ISO_PATTERN.test(session.trainingEndedAt))
  ) return null
  if (session.trainingEndedAt && !session.trainingStartedAt) return null
  if (
    session.trainingStartedAt &&
    session.trainingEndedAt &&
    Date.parse(session.trainingEndedAt) <= Date.parse(session.trainingStartedAt)
  ) return null

  const segments = session.segments.map((segment, index) => normalizeSegment(segment, index))
  if (segments.some((segment) => segment === null)) return null
  const normalizedSegments = segments as PendingShoulderPressSegment[]
  const actualDurationMs = normalizedSegments.reduce((total, segment) => total + segment.durationMs, 0)
  if (session.actualDurationMs !== actualDurationMs) return null
  if (
    session.finalized &&
    normalizedSegments.some((segment) => (
      !isCompressedShoulderPressSegment(segment) || segment.uploadState !== 'uploaded'
    ))
  ) return null

  return {
    clientSessionId: session.clientSessionId,
    ...(isPositiveInteger(session.videoId) ? { videoId: session.videoId } : {}),
    actionId: session.actionId,
    trainingDate: session.trainingDate,
    ...(session.trainingStartedAt ? { trainingStartedAt: session.trainingStartedAt } : {}),
    ...(session.trainingEndedAt ? { trainingEndedAt: session.trainingEndedAt } : {}),
    expectedDurationSeconds: normalizeShoulderPressExpectedDurationSeconds(
      session.expectedDurationSeconds
    ),
    actualDurationMs,
    segments: normalizedSegments,
    finalized: session.finalized,
    createdAt: session.createdAt,
    ...(typeof session.lastError === 'string' ? { lastError: session.lastError } : {})
  }
}

export function savePendingShoulderPressSession(
  storage: StorageLike,
  payload: PendingShoulderPressSession
): void {
  storage.setStorageSync(PENDING_SHOULDER_PRESS_SESSION_KEY, payload)
}

export function loadPendingShoulderPressSession(storage: StorageLike): PendingShoulderPressSession | null {
  return normalizeSession(storage.getStorageSync(PENDING_SHOULDER_PRESS_SESSION_KEY))
}

export function clearPendingShoulderPressSession(storage: StorageLike): void {
  storage.removeStorageSync(PENDING_SHOULDER_PRESS_SESSION_KEY)
}

export function buildPendingShoulderPressUpload(input: {
  actionId: number
  tempFilePath: string
  videoInfo: VideoInfo
  createdAt?: number
}): PendingShoulderPressUpload {
  const date = new Date(input.createdAt ?? Date.now())
  const trainingDate = [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0')
  ].join('-')
  const session = appendPendingSegment(createPendingShoulderPressSession({
    actionId: input.actionId,
    expectedDurationSeconds: Math.max(1, Math.round(input.videoInfo.duration)),
    trainingDate,
    createdAt: input.createdAt
  }), {
    savedFilePath: input.tempFilePath,
    durationSeconds: input.videoInfo.duration,
    sizeKb: input.videoInfo.size
  })
  return {
    ...session,
    tempFilePath: input.tempFilePath,
    durationSeconds: Math.max(1, Math.round(input.videoInfo.duration)),
    sizeBytes: session.segments[0].sizeBytes
  }
}

export function savePendingShoulderPressUpload(
  storage: StorageLike,
  payload: PendingShoulderPressUpload
): void {
  savePendingShoulderPressSession(storage, payload)
}

export function loadPendingShoulderPressUpload(storage: StorageLike): PendingShoulderPressUpload | null {
  const session = loadPendingShoulderPressSession(storage)
  if (!session) return null
  const firstSegment = session.segments[0]
  return {
    ...session,
    ...(firstSegment && isCompressedShoulderPressSegment(firstSegment) ? {
      tempFilePath: firstSegment.savedFilePath,
      durationSeconds: Math.max(1, Math.round(firstSegment.durationMs / 1000)),
      sizeBytes: firstSegment.sizeBytes,
      hash: firstSegment.sha256
    } : {})
  }
}

export function clearPendingShoulderPressUpload(storage: StorageLike): void {
  clearPendingShoulderPressSession(storage)
}

export function hasShoulderPressUploadIntent(pending: PendingShoulderPressUpload): boolean {
  return isPositiveInteger(pending.videoId)
}

export function clearShoulderPressUploadIntent(
  pending: PendingShoulderPressUpload
): PendingShoulderPressUpload {
  const { videoId: _videoId, ...rest } = pending
  return rest
}
