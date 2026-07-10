import type { CurrentPrescription } from '../../types/patientApp'
import { SHOULDER_PRESS_SOURCE_KEY, type PendingShoulderPressSegment } from './session'
import type { ShoulderPressUploadPhase } from './workflow'

export type ShoulderPressAction = NonNullable<CurrentPrescription>['actions'][number]
export type UploadStageState = 'pending' | 'active' | 'done'
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
  return Number.isFinite(actualDurationMs) && actualDurationMs >= SHOULDER_PRESS_HARD_LIMIT_MS
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

export function uploadStageStates(input: {
  hasIntent: boolean
  hasHash: boolean
  activePhase: ShoulderPressUploadPhase | null
}): [UploadStageState, UploadStageState, UploadStageState] {
  const credential: UploadStageState = input.hasIntent
    ? 'done'
    : input.activePhase === 'credential' ? 'active' : 'pending'
  const upload: UploadStageState = input.hasHash
    ? 'done'
    : input.activePhase === 'upload' ? 'active' : 'pending'
  const complete: UploadStageState = input.activePhase === 'complete' ? 'active' : 'pending'
  return [credential, upload, complete]
}
