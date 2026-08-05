import type { CurrentPrescription } from '../../types/patientApp'

let hasCachedValue = false
let cachedValue: CurrentPrescription = null

export function readCurrentPrescriptionCache(): CurrentPrescription | undefined {
  return hasCachedValue ? cachedValue : undefined
}

export function writeCurrentPrescriptionCache(value: CurrentPrescription): void {
  cachedValue = value
  hasCachedValue = true
}

export function clearCurrentPrescriptionCache(): void {
  cachedValue = null
  hasCachedValue = false
}
