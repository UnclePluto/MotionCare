import type { CurrentPrescription } from '../../types/patientApp'

import { isOfficialMotionSourceKey } from './catalog'

type PrescriptionAction = NonNullable<CurrentPrescription>['actions'][number]

export function resolveMotionTrainingAction(
  prescription: CurrentPrescription,
  actionId: number
): PrescriptionAction | null {
  if (!prescription || !Number.isInteger(actionId) || actionId <= 0) return null

  const action = prescription.actions.find((candidate) => candidate.id === actionId)
  if (!action || action.internal_type !== 'motion' || !isOfficialMotionSourceKey(action.source_key)) {
    return null
  }
  return action
}

function withActionId(path: string, actionId: number): string {
  return `${path}?actionId=${encodeURIComponent(String(actionId))}`
}

export function buildMotionTrainingGuideUrl(actionId: number): string {
  return withActionId('/pages/motion-training/index', actionId)
}

export function buildMotionTrainingPreviewUrl(actionId: number): string {
  return withActionId('/pages/motion-training/preview', actionId)
}

export function buildMotionTrainingCameraUrl(actionId: number): string {
  return withActionId('/pages/motion-training/camera', actionId)
}

export function buildMotionTrainingUploadUrl(): string {
  return '/pages/motion-training/upload'
}
