import { clearTrainingDiagnosticQueue, diagnosticUuid, getTrainingDiagnosticScope } from '../features/motion-training/diagnosticScope'
import Taro from '@tarojs/taro'

import { clearCurrentPrescriptionCache } from '../pages/prescription/cache'

const TOKEN_KEY = 'motioncare_patient_app_token'

export function getPatientAppToken(): string | undefined {
  const saved = Taro.getStorageSync(TOKEN_KEY)
  if (typeof saved === 'string') return saved || undefined
  return saved && typeof saved.token === 'string' ? saved.token || undefined : undefined
}

export function setPatientAppToken(token: string) {
  const sameLogin = getPatientAppToken() === token
  let diagnosticScope = diagnosticUuid()
  if (sameLogin) {
    try { diagnosticScope = getTrainingDiagnosticScope(token) } catch { /* repair malformed auth scope without blocking login */ }
  }
  clearCurrentPrescriptionCache()
  Taro.setStorageSync(TOKEN_KEY, { token, diagnosticScope })
  if (!sameLogin) clearTrainingDiagnosticQueue()
}

export function clearPatientAppToken() {
  clearTrainingDiagnosticQueue()
  clearCurrentPrescriptionCache()
  Taro.removeStorageSync(TOKEN_KEY)
}
