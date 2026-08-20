import type { CurrentPrescription } from '../../types/patientApp'
import {
  buildMotionTrainingUploadUrl,
  isCompressedMotionTrainingSegment,
  loadPendingMotionTrainingSession,
  savePendingMotionTrainingSession,
  type PendingMotionTrainingSegment,
  type PendingMotionTrainingSession
} from './session'

export { resolveMotionTrainingAction } from './action'

export type MotionTrainingAction = NonNullable<CurrentPrescription>['actions'][number]
export type TrainingVideoStatus = (
  'recording'
  | 'uploading_segments'
  | 'queued'
  | 'assembling'
  | 'uploading_qiniu'
  | 'attached'
  | 'failed'
  | 'expired'
)

export const MOTION_TRAINING_HARD_LIMIT_MS = 1_800_000
export const MOTION_TRAINING_RECORDING_STOP_MS = 1_797_000

export type MotionTrainingPreviewVisibility = 'visible' | 'hidden'

type MotionTrainingStorage = {
  getStorageSync: (key: string) => unknown
  setStorageSync: (key: string, value: unknown) => void
  removeStorageSync: (key: string) => void
}

type MotionTrainingNavigator = MotionTrainingStorage & {
  getCurrentPages?: () => Array<{ route?: string }>
  reLaunch: (input: { url: string }) => Promise<unknown> | unknown
}

const backgroundUploads = new Set<Promise<void>>()

export function canStartMotionTrainingRecording(input: {
  actionReady: boolean
  cameraReady: boolean
  busy: boolean
}): boolean {
  return input.actionReady && input.cameraReady && !input.busy
}

export function remainingMotionTrainingSeconds(
  actualDurationMs: number,
  expectedDurationSeconds: number
): number {
  const elapsedSeconds = Math.max(0, Math.floor(actualDurationMs / 1000))
  const expectedSeconds = Math.max(1, Math.round(expectedDurationSeconds))
  return Math.max(0, expectedSeconds - elapsedSeconds)
}

export function shouldAutoFinishMotionTraining(input: {
  actualDurationMs: number
  expectedDurationSeconds: number
}): boolean {
  if (!Number.isFinite(input.actualDurationMs)) return false
  const expectedMs = Math.max(1, Math.round(input.expectedDurationSeconds)) * 1000
  return input.actualDurationMs >= expectedMs ||
    input.actualDurationMs >= MOTION_TRAINING_RECORDING_STOP_MS
}

export function nextMotionTrainingPreviewVisibility(input: {
  visibility: MotionTrainingPreviewVisibility
  deltaX: number
  deltaY: number
  threshold?: number
}): MotionTrainingPreviewVisibility {
  const threshold = input.threshold ?? 40
  if (Math.abs(input.deltaX) < threshold || Math.abs(input.deltaX) <= Math.abs(input.deltaY)) {
    return input.visibility
  }
  if (input.visibility === 'visible' && input.deltaX > 0) return 'hidden'
  if (input.visibility === 'hidden' && input.deltaX < 0) return 'visible'
  return input.visibility
}

export function computeMotionTrainingEffectiveDuration(input: {
  savedDurationMs: number
  recording: boolean
  recordingBaseDurationMs: number
  recordingStartedAtMs: number
  nowMs: number
}): number {
  const savedDurationMs = Number.isFinite(input.savedDurationMs)
    ? Math.max(0, Math.round(input.savedDurationMs))
    : 0
  const baseDurationMs = Number.isFinite(input.recordingBaseDurationMs)
    ? Math.max(0, Math.round(input.recordingBaseDurationMs))
    : savedDurationMs

  if (!input.recording || !Number.isFinite(input.recordingStartedAtMs) || input.recordingStartedAtMs <= 0) {
    return Math.min(savedDurationMs, MOTION_TRAINING_HARD_LIMIT_MS)
  }

  const liveDurationMs = Math.max(0, Math.round(input.nowMs - input.recordingStartedAtMs))
  return Math.min(baseDurationMs + liveDurationMs, MOTION_TRAINING_HARD_LIMIT_MS)
}

export function formatMotionTrainingTimer(actualDurationMs: number): string {
  const totalSeconds = Math.max(0, Math.min(
    Math.floor(actualDurationMs / 1000),
    Math.floor(MOTION_TRAINING_HARD_LIMIT_MS / 1000)
  ))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

export function motionTrainingUploadCounters(
  segments: PendingMotionTrainingSegment[]
): { uploaded: number; total: number; percent: number } {
  const total = segments.length
  const uploaded = segments.filter((segment) => (
    isCompressedMotionTrainingSegment(segment) && segment.uploadState === 'uploaded'
  )).length
  return {
    uploaded,
    total,
    percent: total > 0 ? Math.round((uploaded / total) * 100) : 0
  }
}

export function isServerSafeFinalizeStatus(status: TrainingVideoStatus | string): boolean {
  return status === 'queued' ||
    status === 'assembling' ||
    status === 'uploading_qiniu' ||
    status === 'attached'
}

export function isServerRetryableFinalizeStatus(status: TrainingVideoStatus | string): boolean {
  return status === 'failed' || status === 'expired'
}

export function registerMotionTrainingBackgroundUpload(promise: Promise<void>): Promise<void> {
  const tracked = promise
    .catch(() => undefined)
    .finally(() => {
      backgroundUploads.delete(tracked)
    })
  backgroundUploads.add(tracked)
  return promise
}

export async function waitForMotionTrainingBackgroundUploadSettled(): Promise<void> {
  while (backgroundUploads.size > 0) {
    await Promise.allSettled([...backgroundUploads])
  }
}

export function loadOwnedPendingMotionTrainingSession(
  storage: MotionTrainingStorage,
  clientSessionId: string
): PendingMotionTrainingSession | null {
  const current = loadPendingMotionTrainingSession(storage)
  if (!current || current.finalized || current.clientSessionId !== clientSessionId) return null
  return current
}

export function saveOwnedPendingMotionTrainingSession(
  storage: MotionTrainingStorage,
  session: PendingMotionTrainingSession
): PendingMotionTrainingSession | null {
  if (!loadOwnedPendingMotionTrainingSession(storage, session.clientSessionId)) return null
  savePendingMotionTrainingSession(storage, session)
  return session
}

export function isMotionTrainingUploadRoute(route: string | undefined | null): boolean {
  if (!route) return false
  const normalized = route.startsWith('/') ? route : `/${route}`
  return normalized.split('?')[0] === buildMotionTrainingUploadUrl()
}

export function isMotionTrainingCameraRoute(route: string | undefined | null): boolean {
  if (!route) return false
  const normalized = route.startsWith('/') ? route : `/${route}`
  return normalized.split('?')[0] === '/pages/motion-training/camera'
}

function currentRoute(taro: MotionTrainingNavigator): string {
  try {
    const pages = taro.getCurrentPages?.() ?? []
    return pages[pages.length - 1]?.route ?? ''
  } catch {
    return ''
  }
}

function isMotionTrainingRecoveryRoute(
  route: string,
  preserveActiveCameraRoute: boolean
): boolean {
  return isMotionTrainingUploadRoute(route) || (
    preserveActiveCameraRoute && isMotionTrainingCameraRoute(route)
  )
}

export async function reLaunchPendingMotionTrainingUploadIfNeeded(
  taro: MotionTrainingNavigator,
  options: { preserveActiveCameraRoute?: boolean } = {}
): Promise<boolean> {
  const pending = loadPendingMotionTrainingSession(taro)
  if (!pending || pending.finalized) return false
  const preserveActiveCameraRoute = options.preserveActiveCameraRoute ?? false
  if (isMotionTrainingRecoveryRoute(currentRoute(taro), preserveActiveCameraRoute)) return true

  try {
    await waitForMotionTrainingBackgroundUploadSettled()
  } catch {
    // The forced page owns recovery if the background workflow cannot settle cleanly.
  }

  const latest = loadPendingMotionTrainingSession(taro)
  if (!latest || latest.finalized) return false
  if (isMotionTrainingRecoveryRoute(currentRoute(taro), preserveActiveCameraRoute)) return true

  await taro.reLaunch({ url: buildMotionTrainingUploadUrl() })
  return true
}

export async function handlePendingMotionTrainingUploadOnAppShow(
  taro: MotionTrainingNavigator
): Promise<boolean> {
  return reLaunchPendingMotionTrainingUploadIfNeeded(taro, {
    preserveActiveCameraRoute: true
  })
}
