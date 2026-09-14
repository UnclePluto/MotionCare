import Taro from '@tarojs/taro'

export const DIAGNOSTIC_QUEUE_KEY = 'motioncare_training_diagnostics_v1'

export function diagnosticUuid(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
    const random = Math.floor(Math.random() * 16)
    return (character === 'x' ? random : (random & 3) | 8).toString(16)
  })
}

export const PATIENT_TOKEN_KEY = 'motioncare_patient_app_token'

// The credential and its opaque scope share one auth-owned atomic storage value.
// Failed diagnostic cleanup can therefore never reassign old events to a new login.
export function getTrainingDiagnosticScope(token: string): string {
  const saved = Taro.getStorageSync(PATIENT_TOKEN_KEY)
  if (saved && typeof saved === 'object' && saved.token === token
    && typeof saved.diagnosticScope === 'string' && /^[a-f0-9-]{36}$/.test(saved.diagnosticScope)) return saved.diagnosticScope
  if (saved !== token) throw new Error('Diagnostic login scope unavailable')
  const scope = diagnosticUuid()
  Taro.setStorageSync(PATIENT_TOKEN_KEY, { token, diagnosticScope: scope })
  return scope
}

export function clearTrainingDiagnosticQueue(): void {
  try { Taro.removeStorageSync(DIAGNOSTIC_QUEUE_KEY) } catch { /* scope isolates any leftovers */ }
}
