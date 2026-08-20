export const PENDING_MOTION_TRAINING_SESSION_KEY = 'motioncare.pendingMotionTrainingSession'
export const LEGACY_PENDING_SHOULDER_PRESS_SESSION_KEY = 'motioncare.pendingShoulderPressSession'
export const LEGACY_SHOULDER_PRESS_SOURCE_KEY = 'motion-resistance-shoulder-press'
export const LEGACY_PENDING_MOTION_TRAINING_SESSION_KEY = LEGACY_PENDING_SHOULDER_PRESS_SESSION_KEY
export const PENDING_MOTION_TRAINING_UPLOAD_KEY = PENDING_MOTION_TRAINING_SESSION_KEY

export type LegacyPendingCompressionMotionTrainingSegment = {
  index: number
  compressionState: 'pending_compression' | 'compression_failed'
  rawSavedFilePath: string
  durationMs: number
  compressionError?: string
}

export type CompressedMotionTrainingSegment = {
  index: number
  compressionState: 'compressed'
  savedFilePath: string
  durationMs: number
  sizeBytes: number
  uploadState: 'pending' | 'uploading' | 'uploaded'
  localFileState?: 'temporary' | 'save_failed' | 'saved'
  sha256?: string
}

export type PendingMotionTrainingSegment =
  | LegacyPendingCompressionMotionTrainingSegment
  | CompressedMotionTrainingSegment

export type PendingMotionTrainingSession = {
  clientSessionId: string
  videoId?: number
  actionId: number
  trainingDate: string
  trainingStartedAt?: string
  trainingEndedAt?: string
  expectedDurationSeconds: number
  actualDurationMs: number
  segments: PendingMotionTrainingSegment[]
  finalized: boolean
  createdAt: number
  lastError?: string
}

export type PendingMotionTrainingUpload = PendingMotionTrainingSession & {
  tempFilePath?: string
  durationSeconds?: number
  sizeBytes?: number
  hash?: string
}

export type StorageLike = {
  getStorageSync: (key: string) => unknown
  setStorageSync: (key: string, value: unknown) => void
  removeStorageSync: (key: string) => void
}

type VideoInfo = {
  duration: number
  size: number
}

const UUID_V4_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const OFFSET_ISO_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{3}))?(?:Z|([+-])(\d{2}):(\d{2}))$/
const MAX_MOTION_TRAINING_MANIFEST_DURATION_MS = 1_800_000

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

export function isUsableTempVideoPath(value: unknown): value is string {
  if (!isNonEmptyString(value) || /\s/.test(value)) return false
  return /^(?:wxfile|https?|file):\/\//.test(value) || value.startsWith('blob:') || value.startsWith('/')
}

function isTrainingDate(value: unknown): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
}

function parseOffsetIsoTimestamp(value: unknown): number | null {
  if (!isNonEmptyString(value)) return null
  const match = OFFSET_ISO_PATTERN.exec(value)
  if (!match) return null

  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const hour = Number(match[4])
  const minute = Number(match[5])
  const second = Number(match[6])
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
  const daysByMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

  if (month < 1 || month > 12 || day < 1 || day > daysByMonth[month - 1]) return null
  if (hour > 23 || minute > 59 || second > 59) return null
  if (match[8] && (Number(match[9]) > 23 || Number(match[10]) > 59)) return null

  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? timestamp : null
}

export function normalizeMotionTrainingExpectedDurationSeconds(value: number): number {
  if (!Number.isFinite(value)) return 1
  return Math.min(1800, Math.max(1, Math.round(value)))
}

export function isCompressedMotionTrainingSegment(
  segment: PendingMotionTrainingSegment
): segment is CompressedMotionTrainingSegment {
  return segment.compressionState === 'compressed'
}

function normalizeSegment(value: unknown, expectedIndex: number): PendingMotionTrainingSegment | null {
  if (!value || typeof value !== 'object') return null
  const segment = value as Record<string, unknown>
  if (segment.index !== expectedIndex || !isPositiveInteger(segment.durationMs)) return null
  if (
    segment.compressionState === 'pending_compression' ||
    segment.compressionState === 'compression_failed'
  ) {
    if (!isUsableTempVideoPath(segment.rawSavedFilePath)) return null
    if (segment.compressionState === 'compression_failed' && !isNonEmptyString(segment.compressionError)) {
      return null
    }
    return {
      index: expectedIndex,
      compressionState: segment.compressionState,
      rawSavedFilePath: segment.rawSavedFilePath,
      durationMs: segment.durationMs,
      ...(isNonEmptyString(segment.compressionError) ? { compressionError: segment.compressionError } : {})
    }
  }

  if (segment.compressionState !== undefined && segment.compressionState !== 'compressed') return null
  if (!isUsableTempVideoPath(segment.savedFilePath) || !isPositiveInteger(segment.sizeBytes)) return null
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

function normalizePendingMotionTrainingSession(value: unknown): PendingMotionTrainingSession | null {
  if (!value || typeof value !== 'object') return null
  const session = value as Partial<PendingMotionTrainingSession>
  if (!isNonEmptyString(session.clientSessionId) || !UUID_V4_PATTERN.test(session.clientSessionId)) return null
  if (!isPositiveInteger(session.actionId) || !isTrainingDate(session.trainingDate)) return null
  if (!isPositiveNumber(session.expectedDurationSeconds) || !isNonNegativeInteger(session.actualDurationMs)) return null
  if (!Array.isArray(session.segments) || typeof session.finalized !== 'boolean' || !isPositiveNumber(session.createdAt)) {
    return null
  }
  const trainingStartedAtMs = session.trainingStartedAt === undefined
    ? undefined
    : parseOffsetIsoTimestamp(session.trainingStartedAt)
  const trainingEndedAtMs = session.trainingEndedAt === undefined
    ? undefined
    : parseOffsetIsoTimestamp(session.trainingEndedAt)
  if (trainingStartedAtMs === null || trainingEndedAtMs === null) return null
  if (trainingEndedAtMs !== undefined && trainingStartedAtMs === undefined) return null
  if (
    trainingStartedAtMs !== undefined &&
    trainingEndedAtMs !== undefined &&
    trainingEndedAtMs <= trainingStartedAtMs
  ) return null

  const segments = session.segments.map((segment, index) => normalizeSegment(segment, index))
  if (segments.some((segment) => segment === null)) return null
  const normalizedSegments = segments as PendingMotionTrainingSegment[]
  const actualDurationMs = normalizedSegments.reduce((total, segment) => total + segment.durationMs, 0)
  if (
    session.actualDurationMs !== actualDurationMs ||
    actualDurationMs > MAX_MOTION_TRAINING_MANIFEST_DURATION_MS
  ) return null
  if (
    session.finalized &&
    normalizedSegments.some((segment) => (
      !isCompressedMotionTrainingSegment(segment) || segment.uploadState !== 'uploaded'
    ))
  ) return null

  return {
    clientSessionId: session.clientSessionId,
    ...(isPositiveInteger(session.videoId) ? { videoId: session.videoId } : {}),
    actionId: session.actionId,
    trainingDate: session.trainingDate,
    ...(session.trainingStartedAt ? { trainingStartedAt: session.trainingStartedAt } : {}),
    ...(session.trainingEndedAt ? { trainingEndedAt: session.trainingEndedAt } : {}),
    expectedDurationSeconds: normalizeMotionTrainingExpectedDurationSeconds(session.expectedDurationSeconds),
    actualDurationMs,
    segments: normalizedSegments,
    finalized: session.finalized,
    createdAt: session.createdAt,
    ...(typeof session.lastError === 'string' ? { lastError: session.lastError } : {})
  }
}

export function savePendingMotionTrainingSession(
  storage: StorageLike,
  payload: PendingMotionTrainingSession
): void {
  storage.setStorageSync(PENDING_MOTION_TRAINING_SESSION_KEY, payload)
}

export function loadPendingMotionTrainingSession(
  storage: StorageLike
): PendingMotionTrainingSession | null {
  const current = normalizePendingMotionTrainingSession(
    storage.getStorageSync(PENDING_MOTION_TRAINING_SESSION_KEY)
  )
  if (current) return current

  const legacy = normalizePendingMotionTrainingSession(
    storage.getStorageSync(LEGACY_PENDING_SHOULDER_PRESS_SESSION_KEY)
  )
  if (legacy) storage.setStorageSync(PENDING_MOTION_TRAINING_SESSION_KEY, legacy)
  return legacy
}

export function clearPendingMotionTrainingSession(storage: StorageLike): void {
  storage.removeStorageSync(PENDING_MOTION_TRAINING_SESSION_KEY)
  storage.removeStorageSync(LEGACY_PENDING_SHOULDER_PRESS_SESSION_KEY)
}

function assertValidClientSessionId(value: string): void {
  if (!UUID_V4_PATTERN.test(value)) throw new Error('录像会话标识无效')
}

export function createClientSessionId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (marker) => {
    const value = marker === 'x'
      ? Math.floor(Math.random() * 16)
      : Math.floor(Math.random() * 4) + 8
    return value.toString(16)
  })
}

export function buildMotionTrainingSessionUrl(actionId: number): string {
  return `/pages/motion-training/index?actionId=${encodeURIComponent(String(actionId))}`
}

export function buildMotionTrainingCameraUrl(actionId: number): string {
  return `/pages/motion-training/camera?actionId=${encodeURIComponent(String(actionId))}`
}

export function buildMotionTrainingPreviewUrl(actionId: number): string {
  return `/pages/motion-training/preview?actionId=${encodeURIComponent(String(actionId))}`
}

export function buildMotionTrainingUploadUrl(): string {
  return '/pages/motion-training/upload'
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

export function createPendingMotionTrainingSession(input: {
  actionId: number
  expectedDurationSeconds: number
  trainingDate: string
  clientSessionId?: string
  createdAt?: number
}): PendingMotionTrainingSession {
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
    expectedDurationSeconds: normalizeMotionTrainingExpectedDurationSeconds(
      input.expectedDurationSeconds
    ),
    actualDurationMs: 0,
    segments: [],
    finalized: false,
    createdAt
  }
}

export function markMotionTrainingStarted(
  session: PendingMotionTrainingSession,
  nowMs: number,
  offsetMinutes?: number
): PendingMotionTrainingSession {
  if (session.trainingStartedAt) return session
  const moment = clientTrainingMoment(nowMs, offsetMinutes)
  return {
    ...session,
    trainingDate: moment.trainingDate,
    trainingStartedAt: moment.timestamp
  }
}

export function requireMotionTrainingStartedAt(
  session: PendingMotionTrainingSession
): string {
  if (!session.trainingStartedAt) {
    throw new Error('训练开始时间缺失，请重新训练')
  }
  return session.trainingStartedAt
}

export function markMotionTrainingEnded(
  session: PendingMotionTrainingSession,
  nowMs: number,
  offsetMinutes?: number
): PendingMotionTrainingSession {
  if (!session.trainingStartedAt) throw new Error('训练开始时间缺失，请重新训练')
  if (session.trainingEndedAt) return session
  const moment = clientTrainingMoment(nowMs, offsetMinutes)
  const startedAtMs = parseOffsetIsoTimestamp(session.trainingStartedAt)
  const endedAtMs = parseOffsetIsoTimestamp(moment.timestamp)
  if (startedAtMs === null || endedAtMs === null || endedAtMs <= startedAtMs) {
    throw new Error('训练结束时间必须晚于开始时间')
  }
  return { ...session, trainingEndedAt: moment.timestamp }
}

export function appendPendingSegment(
  session: PendingMotionTrainingSession,
  input: {
    savedFilePath: string
    durationSeconds: number
    sizeKb: number
  }
): PendingMotionTrainingSession {
  if (!isUsableTempVideoPath(input.savedFilePath)) throw new Error('录像文件路径无效')
  if (!isPositiveNumber(input.durationSeconds)) throw new Error('录像时长无效')
  if (!isPositiveNumber(input.sizeKb)) throw new Error('录像文件大小无效')

  return appendUploadableMotionTrainingSegment(session, {
    filePath: input.savedFilePath,
    durationMs: Math.max(1, Math.round(input.durationSeconds * 1000)),
    sizeBytes: Math.max(1, Math.round(input.sizeKb * 1024)),
    localFileState: 'saved'
  })
}

export function appendUploadableMotionTrainingSegment(
  session: PendingMotionTrainingSession,
  input: {
    filePath: string
    durationMs: number
    sizeBytes: number
    localFileState: 'temporary' | 'save_failed' | 'saved'
  }
): PendingMotionTrainingSession {
  if (!isUsableTempVideoPath(input.filePath)) throw new Error('录像文件路径无效')
  if (!isPositiveInteger(input.durationMs)) throw new Error('录像时长无效')
  if (!isPositiveInteger(input.sizeBytes)) throw new Error('录像文件大小无效')
  if (session.actualDurationMs + input.durationMs > MAX_MOTION_TRAINING_MANIFEST_DURATION_MS) {
    throw new Error('录像总时长超过限制，请重新录制')
  }
  const segment: CompressedMotionTrainingSegment = {
    index: session.segments.length,
    compressionState: 'compressed',
    savedFilePath: input.filePath,
    durationMs: input.durationMs,
    sizeBytes: input.sizeBytes,
    uploadState: 'pending',
    localFileState: input.localFileState
  }

  return {
    ...session,
    actualDurationMs: session.actualDurationMs + input.durationMs,
    segments: [...session.segments, segment],
    lastError: undefined
  }
}

export function promoteLegacyMotionTrainingSegment(
  session: PendingMotionTrainingSession,
  index: number,
  input: {
    savedFilePath: string
    durationMs: number
    sizeBytes: number
    localFileState?: 'temporary' | 'save_failed' | 'saved'
  }
): PendingMotionTrainingSession {
  if (!isUsableTempVideoPath(input.savedFilePath)) throw new Error('录像文件路径无效')
  if (!isPositiveInteger(input.durationMs)) throw new Error('录像时长无效')
  if (!isPositiveInteger(input.sizeBytes)) throw new Error('录像文件大小无效')
  const current = session.segments[index]
  if (!current || current.index !== index || isCompressedMotionTrainingSegment(current)) {
    throw new Error('待上传录像分段不存在')
  }
  const actualDurationMs = session.actualDurationMs - current.durationMs + input.durationMs
  if (actualDurationMs > MAX_MOTION_TRAINING_MANIFEST_DURATION_MS) {
    throw new Error('录像总时长超过限制，请重新录制')
  }

  return {
    ...session,
    actualDurationMs,
    segments: session.segments.map((segment) => (
      segment.index === index
        ? {
            index,
            compressionState: 'compressed' as const,
            savedFilePath: input.savedFilePath,
            durationMs: input.durationMs,
            sizeBytes: input.sizeBytes,
            uploadState: 'pending' as const,
            localFileState: input.localFileState ?? 'saved'
          }
        : segment
    )),
    lastError: undefined
  }
}

export function markServerUploadedSegments(
  session: PendingMotionTrainingSession,
  uploadedIndexes: number[]
): PendingMotionTrainingSession {
  const uploaded = new Set(uploadedIndexes.filter((index) => Number.isInteger(index) && index >= 0))
  return {
    ...session,
    segments: session.segments.map((segment) => (
      uploaded.has(segment.index) && isCompressedMotionTrainingSegment(segment)
        ? { ...segment, uploadState: 'uploaded' }
        : segment
    ))
  }
}

export function isSegmentReadyForLocalDeletion(segment: PendingMotionTrainingSegment): boolean {
  return isCompressedMotionTrainingSegment(segment) &&
    segment.uploadState === 'uploaded' &&
    isNonEmptyString(segment.sha256)
}

export function buildPendingMotionTrainingUpload(input: {
  actionId: number
  tempFilePath: string
  videoInfo: VideoInfo
  createdAt?: number
}): PendingMotionTrainingUpload {
  const date = new Date(input.createdAt ?? Date.now())
  const trainingDate = [
    date.getFullYear(),
    twoDigits(date.getMonth() + 1),
    twoDigits(date.getDate())
  ].join('-')
  const session = appendPendingSegment(createPendingMotionTrainingSession({
    actionId: input.actionId,
    expectedDurationSeconds: Math.max(1, Math.round(input.videoInfo.duration)),
    trainingDate,
    createdAt: input.createdAt
  }), {
    savedFilePath: input.tempFilePath,
    durationSeconds: input.videoInfo.duration,
    sizeKb: input.videoInfo.size
  })
  const firstSegment = session.segments[0]
  if (!firstSegment || !isCompressedMotionTrainingSegment(firstSegment)) {
    throw new Error('录像上传信息不完整，请重新开始')
  }
  return {
    ...session,
    tempFilePath: input.tempFilePath,
    durationSeconds: Math.max(1, Math.round(input.videoInfo.duration)),
    sizeBytes: firstSegment.sizeBytes
  }
}

export function savePendingMotionTrainingUpload(
  storage: StorageLike,
  payload: PendingMotionTrainingUpload
): void {
  savePendingMotionTrainingSession(storage, payload)
}

export function loadPendingMotionTrainingUpload(
  storage: StorageLike
): PendingMotionTrainingUpload | null {
  const session = loadPendingMotionTrainingSession(storage)
  if (!session) return null
  const firstSegment = session.segments[0]
  return {
    ...session,
    ...(firstSegment && isCompressedMotionTrainingSegment(firstSegment) ? {
      tempFilePath: firstSegment.savedFilePath,
      durationSeconds: Math.max(1, Math.round(firstSegment.durationMs / 1000)),
      sizeBytes: firstSegment.sizeBytes,
      hash: firstSegment.sha256
    } : {})
  }
}

export function clearPendingMotionTrainingUpload(storage: StorageLike): void {
  clearPendingMotionTrainingSession(storage)
}

export function hasMotionTrainingUploadIntent(pending: PendingMotionTrainingUpload): boolean {
  return isPositiveInteger(pending.videoId)
}

export function clearMotionTrainingUploadIntent(
  pending: PendingMotionTrainingUpload
): PendingMotionTrainingUpload {
  const { videoId: _videoId, ...rest } = pending
  return rest
}
