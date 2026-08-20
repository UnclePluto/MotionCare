export const PENDING_MOTION_TRAINING_SESSION_KEY = 'motioncare.pendingMotionTrainingSession'
export const LEGACY_PENDING_SHOULDER_PRESS_SESSION_KEY = 'motioncare.pendingShoulderPressSession'

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

export type StorageLike = {
  getStorageSync: (key: string) => unknown
  setStorageSync: (key: string, value: unknown) => void
  removeStorageSync: (key: string) => void
}

const UUID_V4_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const OFFSET_ISO_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{3}))?(?:Z|([+-])(\d{2}):(\d{2}))$/

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

function isUsableTempVideoPath(value: unknown): value is string {
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

function normalizeExpectedDurationSeconds(value: number): number {
  if (!Number.isFinite(value)) return 1
  return Math.min(2400, Math.max(1, Math.round(value)))
}

function isCompressedMotionTrainingSegment(
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
  if (session.actualDurationMs !== actualDurationMs) return null
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
    expectedDurationSeconds: normalizeExpectedDurationSeconds(session.expectedDurationSeconds),
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
