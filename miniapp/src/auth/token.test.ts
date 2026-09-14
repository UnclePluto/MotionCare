import { beforeEach, expect, it, vi } from 'vitest'
const h = vi.hoisted(() => ({ storage: new Map<string, unknown>(), failDiagnostics: false, request: vi.fn() }))
vi.mock('@tarojs/taro', () => ({ default: {
  request: h.request,
  getStorageSync: (key: string) => h.storage.get(key),
  setStorageSync: (key: string, value: unknown) => { if (h.failDiagnostics && key !== 'motioncare_patient_app_token') throw Error('full'); h.storage.set(key, value) },
  removeStorageSync: (key: string) => { if (h.failDiagnostics && key !== 'motioncare_patient_app_token') throw Error('full'); h.storage.delete(key) }
} }))
vi.mock('../demo/session', () => ({ isDemoSession: () => false }))
vi.mock('../pages/prescription/cache', () => ({ clearCurrentPrescriptionCache: vi.fn() }))
beforeEach(() => { h.storage.clear(); h.failDiagnostics = false; vi.resetModules() })
it('atomically isolates login scope even when diagnostic storage operations fail, including after restart', async () => {
  const auth = await import('./token')
  const scope = await import('../features/motion-training/diagnosticScope')
  auth.setPatientAppToken('old-credential')
  const oldScope = scope.getTrainingDiagnosticScope('old-credential')
  h.storage.set(scope.DIAGNOSTIC_QUEUE_KEY, { scope: oldScope, events: [{ event_id: 'old-event' }] })
  h.failDiagnostics = true
  auth.setPatientAppToken('new-credential')
  expect(auth.getPatientAppToken()).toBe('new-credential')
  expect(scope.getTrainingDiagnosticScope('new-credential')).not.toBe(oldScope)
  vi.resetModules()
  const restarted = await import('../features/motion-training/diagnosticScope')
  expect(restarted.getTrainingDiagnosticScope('new-credential')).not.toBe(oldScope)
  expect(JSON.stringify(h.storage.get(scope.DIAGNOSTIC_QUEUE_KEY))).not.toContain('credential')
})
it('upgrades legacy string credentials and keeps the same scope on cold start', async () => {
  h.storage.set('motioncare_patient_app_token', 'legacy-credential')
  const scope = await import('../features/motion-training/diagnosticScope')
  const id = scope.getTrainingDiagnosticScope('legacy-credential')
  vi.resetModules()
  const auth = await import('./token')
  expect(auth.getPatientAppToken()).toBe('legacy-credential')
  const restarted = await import('../features/motion-training/diagnosticScope')
  expect(restarted.getTrainingDiagnosticScope('legacy-credential')).toBe(id)
  auth.setPatientAppToken('legacy-credential')
  expect(restarted.getTrainingDiagnosticScope('legacy-credential')).toBe(id)
})

it('does not transmit old events under a new credential after failed cleanup and module restart', async () => {
  const auth = await import('./token')
  auth.setPatientAppToken('old-login')
  let diagnostics = await import('../features/motion-training/diagnostics')
  diagnostics.reportTrainingDiagnostic('upload', { errMsg: 'uploadFile:fail timeout' }, { videoId: 11 })
  h.failDiagnostics = true
  auth.setPatientAppToken('new-login')
  vi.resetModules()
  h.request.mockClear()
  diagnostics = await import('../features/motion-training/diagnostics')
  diagnostics.startTrainingDiagnostics()
  for (let i = 0; i < 20; i++) await Promise.resolve()
  diagnostics.stopTrainingDiagnostics()
  expect(h.request).not.toHaveBeenCalled()
})

it('never attributes an old in-flight session creation failure to a newly logged-in patient', async () => {
  h.request.mockReset()
  const auth = await import('./token')
  auth.setPatientAppToken('patient-a')
  const diagnostics = await import('../features/motion-training/diagnostics')
  const api = await import('../features/motion-training/api')
  let rejectRequest!: (error: unknown) => void
  h.request.mockImplementationOnce(() => new Promise((_, reject) => { rejectRequest = reject }))
  const pending = api.createVideoSession({ actionId: 1, clientSessionId: '89a94d4c-bca9-44b5-bfd2-d4104bc17a80', trainingDate: '2026-09-14', expectedDurationSeconds: 60, trainingStartedAt: '2026-09-14T00:00:00Z' })
  const rejected = expect(pending).rejects.toThrow()
  auth.setPatientAppToken('patient-b')
  rejectRequest({ errMsg: 'request:fail timeout' })
  await rejected
  expect(JSON.stringify(h.storage.get('motioncare_training_diagnostics_v1')) ?? '').not.toContain('89a94d4c')
  diagnostics.startTrainingDiagnostics()
  for (let i = 0; i < 20; i++) await Promise.resolve()
  diagnostics.stopTrainingDiagnostics()
  expect(h.request).toHaveBeenCalledTimes(1)
})
