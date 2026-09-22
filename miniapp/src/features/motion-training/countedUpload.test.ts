import { afterEach, beforeEach, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ storage: new Map(), upload: vi.fn(), status: vi.fn(), home: vi.fn(), network: undefined as any }))
vi.mock('@tarojs/taro', () => ({ default: {
  getStorageSync: (key: string) => mocks.storage.get(key), setStorageSync: (key: string, value: unknown) => mocks.storage.set(key, value),
  getFileInfo: async () => ({ size: 1000 }), getFileSystemManager: () => ({ removeSavedFile: (o: any) => o.success() }),
  onNetworkStatusChange: (fn: any) => { mocks.network = fn }, offNetworkStatusChange: () => { mocks.network = undefined }
} }))
vi.mock('../../auth/token', () => ({ getPatientAppToken: () => 'token' }))
vi.mock('../../demo/session', () => ({ isDemoSession: () => false }))
vi.mock('../../demo/patientAppData', () => ({ fetchPatientHomeData: mocks.home }))
vi.mock('../../api/client', () => ({ request: async () => ({ id: 1 }) }))
vi.mock('./api', () => ({ createVideoSession: async () => ({ video_id: 1, status: 'uploading', uploaded_segments: [] }),
  getVideoSessionStatus: mocks.status, uploadVideoSegment: mocks.upload,
  finalizeVideoSession: async () => ({ video_id: 1, status: 'queued' }) }))
import { storeCountedSession, countedSessions, syncCountedQueue, startCountedRetry, stopCountedRetry, countedUploadState } from './countedSession'
const fixture = () => ({ id: 'session', owner: 1, actionId: 1, actionName: '训练', plannedSets: 1, repetitions: 10, countUnit: 'total' as const,
  startedAt: new Date().toISOString(), trainingDate: '2026-09-16', attempts: [{ id: 'attempt', index: 1, startedAt: new Date().toISOString(), endedAt: new Date().toISOString(), completed: true,
    uploadId: 'upload', segments: [{ path: 'video', durationMs: 5000, sizeBytes: 1000 }] }] })
beforeEach(() => { vi.useFakeTimers(); mocks.storage.clear(); mocks.upload.mockReset(); mocks.status.mockReset(); mocks.home.mockResolvedValue({ project_patient_id: 1 }); mocks.status.mockResolvedValue({ video_id: 1, status: 'attached' }) })
afterEach(() => { stopCountedRetry(); vi.useRealTimers() })
it('启动时没有录像，后来新增的完成组也会自动补传并确认完成', async () => {
  startCountedRetry()
  await vi.advanceTimersByTimeAsync(1000)
  storeCountedSession(fixture())
  await vi.advanceTimersByTimeAsync(5000)
  expect(countedSessions(1)[0].attempts[0].uploaded).toBe(true)
})
it('网络失败自动等待重试，服务端确认后才标记已上传', async () => {
  storeCountedSession(fixture())
  mocks.upload.mockRejectedValueOnce(new Error('网络失败')).mockResolvedValue({})
  mocks.status.mockResolvedValueOnce({ video_id: 1, status: 'uploading', uploaded_segments: [] }).mockResolvedValue({ video_id: 1, status: 'attached' })
  startCountedRetry()
  await vi.advanceTimersByTimeAsync(100)
  expect(countedUploadState(1, 'attempt')?.phase).toBe('retrying')
  expect(countedSessions(1)[0].attempts[0].uploaded).not.toBe(true)
  await vi.advanceTimersByTimeAsync(6000)
  expect(countedSessions(1)[0].attempts[0].uploaded).toBe(true)
})
it('显示真实分段字节进度和速度，等待服务端确认不会提前完成', async () => {
  storeCountedSession(fixture())
  mocks.upload.mockImplementation(async (input: any) => {
    await vi.advanceTimersByTimeAsync(1000)
    input.onProgress(50, 500)
    expect(countedUploadState(1, 'attempt')).toMatchObject({ phase: 'uploading', percent: 50, bytesPerSecond: 500 })
  })
  await syncCountedQueue(1)
  expect(countedUploadState(1, 'attempt')?.phase).toBe('confirming')
  expect(countedSessions(1)[0].attempts[0].uploaded).not.toBe(true)
})

it('网络恢复立即重试且停止前台调度后不再后台发送', async () => {
  storeCountedSession(fixture())
  mocks.upload.mockRejectedValueOnce(new Error('网络失败')).mockResolvedValue({})
  mocks.status.mockResolvedValueOnce({ video_id: 1, status: 'uploading', uploaded_segments: [] }).mockResolvedValue({ video_id: 1, status: 'attached' })
  startCountedRetry()
  await vi.advanceTimersByTimeAsync(100)
  expect(countedUploadState(1, 'attempt')?.phase).toBe('retrying')
  mocks.network({ isConnected: true })
  await vi.advanceTimersByTimeAsync(100)
  expect(countedUploadState(1, 'attempt')?.phase).toBe('confirming')
  stopCountedRetry()
  await vi.advanceTimersByTimeAsync(10000)
  expect(countedSessions(1)[0].attempts[0].uploaded).not.toBe(true)
})
