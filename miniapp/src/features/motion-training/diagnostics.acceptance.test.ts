import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const harness = vi.hoisted(() => ({
  storage: new Map<string, unknown>(), token: 'test-login-credential', demo: false,
  getNetworkType: vi.fn(), getDeviceInfo: vi.fn(), getAppBaseInfo: vi.fn(), getAccountInfoSync: vi.fn(),
  request: vi.fn(), onNetworkStatusChange: vi.fn(), offNetworkStatusChange: vi.fn(), setStorageSync: vi.fn(),
}))
vi.mock('@tarojs/taro', () => ({ default: {
  getStorageSync: (key: string) => harness.storage.get(key),
  setStorageSync: (key: string, value: unknown) => harness.setStorageSync(key, value),
  removeStorageSync: (key: string) => harness.storage.delete(key),
  request: harness.request,
  getNetworkType: harness.getNetworkType,
  getDeviceInfo: harness.getDeviceInfo, getAppBaseInfo: harness.getAppBaseInfo,
  getAccountInfoSync: harness.getAccountInfoSync,
  onNetworkStatusChange: harness.onNetworkStatusChange, offNetworkStatusChange: harness.offNetworkStatusChange,
} }))
vi.mock('../../auth/token', () => ({ getPatientAppToken: () => harness.token || undefined }))
vi.mock('../../demo/session', () => ({ isDemoSession: () => harness.demo }))

type Reporter = typeof import('./diagnostics')
let reporter: Reporter
const context = { clientSessionId: '89a94d4c-bca9-44b5-bfd2-d4104bc17a80', videoId: 11, segmentIndex: 0 }
const error = { errMsg: 'uploadFile:fail timeout', errCode: 1001 }
const settle = async () => { for (let i = 0; i < 20; i++) await Promise.resolve() }
const savedText = () => JSON.stringify([...harness.storage.entries()].filter(([key]) => key !== 'motioncare_patient_app_token').map(([, value]) => value))

beforeEach(async () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-09-14T08:00:00Z'))
  vi.resetModules()
  vi.clearAllMocks()
  harness.storage.clear(); harness.token = 'test-login-credential'; harness.demo = false
  harness.getNetworkType.mockResolvedValue({ networkType: 'wifi' })
  harness.getDeviceInfo.mockReturnValue({ platform: 'ios' })
  harness.getAppBaseInfo.mockReturnValue({ SDKVersion: '3.0.0' })
  harness.getAccountInfoSync.mockReturnValue({ miniProgram: { version: '1.0.0' } })
  harness.setStorageSync.mockImplementation((key: string, value: unknown) => harness.storage.set(key, value))
  harness.storage.set('motioncare_patient_app_token', harness.token)
  harness.request.mockRejectedValue({ errMsg: 'request:fail timeout' })
  reporter = await import('./diagnostics')
  reporter.startTrainingDiagnostics()
})
afterEach(() => { reporter?.stopTrainingDiagnostics(); vi.useRealTimers() })

describe('training diagnostic delivery acceptance', () => {
  it('persists a failed upload without throwing when the logging server is offline', async () => {
    expect(() => reporter.reportTrainingDiagnostic('upload', error, context)).not.toThrow()
    await settle()
    expect(savedText()).toContain(context.clientSessionId)
    expect(harness.request).toHaveBeenCalled()
    expect(harness.request.mock.calls[0][0].url).toContain('/patient-app/training-upload-diagnostics/')
    expect(savedText()).not.toContain(harness.token)
  })
  it('replays the same event after a cold start and removes it only after acknowledgement', async () => {
    reporter.reportTrainingDiagnostic('upload', error, context)
    await settle()
    const originalId = harness.request.mock.calls[0][0].data.event_id
    reporter.stopTrainingDiagnostics(); vi.resetModules()
    harness.request.mockImplementation(async (options) => ({ statusCode: 200, data: { event_id: options.data.event_id } }))
    reporter = await import('./diagnostics'); reporter.startTrainingDiagnostics()
    await settle()
    expect(harness.request.mock.calls.at(-1)?.[0].data.event_id).toBe(originalId)
    expect(savedText()).not.toContain(originalId)
  })
  it('retains an event when the server acknowledges a different ID', async () => {
    harness.request.mockResolvedValue({ statusCode: 200, data: { event_id: 'wrong-id' } })
    reporter.reportTrainingDiagnostic('upload', error, context); await settle()
    expect(savedText()).toContain(context.clientSessionId)
  })
  it('drops local events at the fifteen-day boundary before a reconnect can send them', async () => {
    reporter.reportTrainingDiagnostic('upload', error, context); await settle()
    reporter.stopTrainingDiagnostics(); harness.request.mockClear()
    vi.setSystemTime(new Date('2026-09-29T08:00:00Z'))
    reporter.startTrainingDiagnostics(); await settle()
    expect(harness.request).not.toHaveBeenCalled()
    expect(savedText()).not.toContain(context.clientSessionId)
  })
  it('never records or sends diagnostics in demo mode', async () => {
    harness.demo = true
    reporter.reportTrainingDiagnostic('upload', error, context); await settle()
    expect(savedText()).not.toContain(context.clientSessionId)
    expect(harness.request).not.toHaveBeenCalled()
  })
  it('does not affect the caller when local storage is full', async () => {
    harness.setStorageSync.mockImplementation(() => { throw new Error('storage full') })
    expect(() => reporter.reportTrainingDiagnostic('upload', error, context)).not.toThrow()
    await settle()
  })
  it('does not persist credentials, file paths, URLs or response bodies', async () => {
    reporter.reportTrainingDiagnostic('upload', {
      errMsg: 'uploadFile:fail timeout https://host/private.mp4?token=canary-secret wxfile://private/video.mp4',
      token: 'canary-secret', response: { name: 'PRIVATE_BODY_CANARY' },
    }, context); await settle()
    for (const forbidden of ['canary-secret', 'wxfile:', 'https://host', 'PRIVATE_BODY_CANARY']) {
      expect(savedText()).not.toContain(forbidden)
      expect(JSON.stringify(harness.request.mock.calls.map(([options]) => options.data))).not.toContain(forbidden)
    }
  })
  it('keeps a bounded queue after repeated failures without busy retrying', async () => {
    for (let i = 0; i < 130; i++) reporter.reportTrainingDiagnostic('upload', error, context)
    await settle()
    const occurrences = savedText().match(/"event_id"/g) ?? []
    expect(occurrences.length).toBeGreaterThan(0)
    expect(occurrences.length).toBeLessThanOrEqual(100)
    expect(harness.request.mock.calls.length).toBeLessThanOrEqual(2)
  })
  it('serializes reconnect attempts and retries the same event when the ACK is lost', async () => {
    let release!: (value: unknown) => void
    harness.request.mockImplementationOnce(() => new Promise(resolve => { release = resolve }))
    reporter.reportTrainingDiagnostic('upload', error, context)
    const reconnect = harness.onNetworkStatusChange.mock.calls[0][0]
    reconnect({ isConnected: true, networkType: 'wifi' })
    reporter.reportTrainingDiagnostic('status', error, context)
    await settle()
    expect(harness.request).toHaveBeenCalledTimes(1)
    const id = harness.request.mock.calls[0][0].data.event_id
    release({ statusCode: 200, data: {} }); await settle()
    await vi.advanceTimersByTimeAsync(1000)
    expect(harness.request.mock.calls[1][0].data.event_id).toBe(id)
  })
  it('stops timers and reconnect delivery in the background', async () => {
    reporter.reportTrainingDiagnostic('upload', error, context); await settle()
    reporter.stopTrainingDiagnostics()
    await vi.advanceTimersByTimeAsync(120000)
    expect(harness.request).toHaveBeenCalledTimes(1)
    expect(harness.offNetworkStatusChange).toHaveBeenCalled()
    reporter.startTrainingDiagnostics(); await settle()
    expect(harness.request).toHaveBeenCalledTimes(2)
  })
  it('isolates new login events from old in-flight acknowledgements', async () => {
    let release!: (value: unknown) => void
    harness.request.mockImplementationOnce(() => new Promise(resolve => { release = resolve }))
    reporter.reportTrainingDiagnostic('upload', error, context)
    const oldId = harness.request.mock.calls[0][0].data.event_id
    harness.token = 'different-login-credential'
    harness.storage.set('motioncare_patient_app_token', harness.token)
    reporter.reportTrainingDiagnostic('status', error, { videoId: 22 })
    release({ statusCode: 200, data: { event_id: oldId } }); await settle()
    await vi.advanceTimersByTimeAsync(0)
    expect(savedText()).not.toContain(oldId)
    expect(harness.request.mock.calls.at(-1)?.[0].data.video_id).toBe(22)
    expect(savedText()).not.toContain(harness.token)
  })
  it('pauses after auth rejection without clearing credentials or retrying on reconnect', async () => {
    harness.request.mockResolvedValue({ statusCode: 401, data: {} })
    reporter.reportTrainingDiagnostic('upload', error, context); await settle()
    harness.onNetworkStatusChange.mock.calls[0][0]({ isConnected: true, networkType: 'wifi' })
    await vi.advanceTimersByTimeAsync(120000)
    expect(harness.request).toHaveBeenCalledTimes(1)
    expect(harness.token).toBe('test-login-credential')
    expect(savedText()).toContain(context.clientSessionId)
  })

  it('rejects corrupted local event content before replaying after restart', async () => {
    reporter.reportTrainingDiagnostic('upload', error, context); await settle()
    reporter.stopTrainingDiagnostics()
    for (const [key, value] of harness.storage.entries()) {
      if (key.includes('diagnostics_v1')) {
        const queue = value as { events: Array<Record<string, unknown>> }
        queue.events[0].message = 'PRIVATE_RESPONSE_CANARY https://private/path'
      }
    }
    harness.request.mockClear()
    reporter.startTrainingDiagnostics(); await settle()
    expect(harness.request).not.toHaveBeenCalled()
    expect(savedText()).not.toContain('PRIVATE_RESPONSE_CANARY')
  })

  it('uses safe metadata fallbacks and never waits for a stalled network lookup', async () => {
    reporter.stopTrainingDiagnostics()
    harness.getNetworkType.mockImplementation(() => new Promise(() => {}))
    harness.getDeviceInfo.mockImplementation(() => { throw new Error('unavailable') })
    harness.getAppBaseInfo.mockReturnValue({ SDKVersion: '3.0.0-private-person' })
    harness.getAccountInfoSync.mockReturnValue({ miniProgram: { version: '13812345678' } })
    reporter.startTrainingDiagnostics()
    reporter.reportTrainingDiagnostic('compression', { errMsg: 'compressVideo:fail permission denied', errCode: '13812345678' }, context)
    await settle()
    expect(harness.request).toHaveBeenCalled()
    expect(harness.request.mock.calls[0][0].data).toMatchObject({ platform: 'unknown', sdk_version: 'unknown', app_version: 'unknown', error_code: 'compression_permission_denied', message: 'compression: permission denied' })
    expect(savedText()).not.toContain('13812345678')
  })

  it('registers reconnect delivery before the first login on an initially logged-out launch', async () => {
    reporter.stopTrainingDiagnostics(); vi.resetModules()
    harness.token = ''; harness.storage.clear()
    harness.onNetworkStatusChange.mockClear()
    reporter = await import('./diagnostics'); reporter.startTrainingDiagnostics()
    expect(harness.onNetworkStatusChange).toHaveBeenCalledTimes(1)
    harness.token = 'first-login'; harness.storage.set('motioncare_patient_app_token', harness.token)
    reporter.reportTrainingDiagnostic('upload', error, context); await settle()
    harness.request.mockClear()
    harness.onNetworkStatusChange.mock.calls[0][0]({ isConnected: true, networkType: 'wifi' })
    await settle()
    expect(harness.request).toHaveBeenCalledTimes(1)
  })

  it('fails closed when the original asynchronous operation could not capture a login scope', async () => {
    harness.storage.delete('motioncare_patient_app_token')
    const diagnosticScope = reporter.captureTrainingDiagnosticScope()
    expect(diagnosticScope).toBeNull()
    harness.storage.set('motioncare_patient_app_token', harness.token)
    reporter.reportTrainingDiagnostic('file_read', error, { ...context, diagnosticScope })
    await settle()
    expect(savedText()).not.toContain(context.clientSessionId)
    expect(harness.request).not.toHaveBeenCalled()
  })

})
