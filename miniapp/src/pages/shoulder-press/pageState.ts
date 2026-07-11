import type { CurrentPrescription } from '../../types/patientApp'
import {
  buildShoulderPressUploadUrl,
  loadPendingShoulderPressSession,
  savePendingShoulderPressSession,
  SHOULDER_PRESS_SOURCE_KEY,
  type PendingShoulderPressSegment,
  type PendingShoulderPressSession
} from './session'

export type ShoulderPressAction = NonNullable<CurrentPrescription>['actions'][number]
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

export const SHOULDER_PRESS_HARD_LIMIT_MS = 600_000
export const SHOULDER_PRESS_RECORDING_STOP_MS = 597_000

type ShoulderPressStorage = {
  getStorageSync: (key: string) => unknown
  setStorageSync: (key: string, value: unknown) => void
}

type ShoulderPressNavigator = ShoulderPressStorage & {
  getCurrentPages?: () => Array<{ route?: string }>
  reLaunch: (input: { url: string }) => Promise<unknown> | unknown
}

const backgroundUploads = new Set<Promise<void>>()

export function resolveShoulderPressAction(
  prescription: CurrentPrescription,
  actionId: number
): ShoulderPressAction | null {
  if (!Number.isInteger(actionId) || actionId <= 0) return null
  const action = prescription?.actions.find((item) => item.id === actionId) ?? null
  return action?.source_key === SHOULDER_PRESS_SOURCE_KEY ? action : null
}

export function canStartShoulderPressRecording(input: {
  actionReady: boolean
  cameraReady: boolean
  busy: boolean
}): boolean {
  return input.actionReady && input.cameraReady && !input.busy
}

export function canCompleteShoulderPressTraining(input: {
  actualDurationMs: number
  expectedDurationSeconds: number
}): boolean {
  if (!Number.isFinite(input.actualDurationMs) || !Number.isFinite(input.expectedDurationSeconds)) return false
  return input.actualDurationMs >= Math.max(1, Math.round(input.expectedDurationSeconds)) * 1000
}

export function shouldAutoFinishShoulderPressTraining(actualDurationMs: number): boolean {
  return Number.isFinite(actualDurationMs) && actualDurationMs >= SHOULDER_PRESS_RECORDING_STOP_MS
}

export function computeShoulderPressEffectiveDuration(input: {
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
    return Math.min(savedDurationMs, SHOULDER_PRESS_HARD_LIMIT_MS)
  }

  const liveDurationMs = Math.max(0, Math.round(input.nowMs - input.recordingStartedAtMs))
  return Math.min(baseDurationMs + liveDurationMs, SHOULDER_PRESS_HARD_LIMIT_MS)
}

export function formatShoulderPressTimer(actualDurationMs: number): string {
  const totalSeconds = Math.max(0, Math.min(
    Math.floor(actualDurationMs / 1000),
    Math.floor(SHOULDER_PRESS_HARD_LIMIT_MS / 1000)
  ))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

export function shoulderPressUploadCounters(
  segments: Array<Pick<PendingShoulderPressSegment, 'uploadState'>>
): { uploaded: number; total: number; percent: number } {
  const total = segments.length
  const uploaded = segments.filter((segment) => segment.uploadState === 'uploaded').length
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

export function registerShoulderPressBackgroundUpload(promise: Promise<void>): Promise<void> {
  const tracked = promise
    .catch(() => undefined)
    .finally(() => {
      backgroundUploads.delete(tracked)
    })
  backgroundUploads.add(tracked)
  return promise
}

export async function waitForShoulderPressBackgroundUploadSettled(): Promise<void> {
  while (backgroundUploads.size > 0) {
    await Promise.allSettled([...backgroundUploads])
  }
}

export function loadOwnedPendingShoulderPressSession(
  storage: ShoulderPressStorage,
  clientSessionId: string
): PendingShoulderPressSession | null {
  const current = loadPendingShoulderPressSession(storage)
  if (!current || current.finalized || current.clientSessionId !== clientSessionId) return null
  return current
}

export function saveOwnedPendingShoulderPressSession(
  storage: ShoulderPressStorage,
  session: PendingShoulderPressSession
): PendingShoulderPressSession | null {
  if (!loadOwnedPendingShoulderPressSession(storage, session.clientSessionId)) return null
  savePendingShoulderPressSession(storage, session)
  return session
}

export function isShoulderPressUploadRoute(route: string | undefined | null): boolean {
  if (!route) return false
  const normalized = route.startsWith('/') ? route : `/${route}`
  return normalized.split('?')[0] === buildShoulderPressUploadUrl()
}

function currentRoute(taro: ShoulderPressNavigator): string {
  try {
    const pages = taro.getCurrentPages?.() ?? []
    return pages[pages.length - 1]?.route ?? ''
  } catch {
    return ''
  }
}

export async function reLaunchPendingShoulderPressUploadIfNeeded(
  taro: ShoulderPressNavigator
): Promise<boolean> {
  const pending = loadPendingShoulderPressSession(taro)
  if (!pending || pending.finalized) return false
  if (isShoulderPressUploadRoute(currentRoute(taro))) return true

  try {
    await waitForShoulderPressBackgroundUploadSettled()
  } catch {
    // The forced page owns recovery if the background workflow cannot settle cleanly.
  }

  const latest = loadPendingShoulderPressSession(taro)
  if (!latest || latest.finalized) return false
  if (isShoulderPressUploadRoute(currentRoute(taro))) return true

  await taro.reLaunch({ url: buildShoulderPressUploadUrl() })
  return true
}
