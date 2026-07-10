import type { CurrentPrescription } from '../../types/patientApp'
import { SHOULDER_PRESS_SOURCE_KEY } from './session'
import type { ShoulderPressUploadPhase } from './workflow'

export type ShoulderPressAction = NonNullable<CurrentPrescription>['actions'][number]
export type UploadStageState = 'pending' | 'active' | 'done'

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
