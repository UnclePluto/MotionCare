import { beforeEach, expect, it, vi } from 'vitest'
const m = vi.hoisted(() => ({ storage: new Map(), request: vi.fn(), upload: vi.fn(), legacy: vi.fn(), info: vi.fn(), remove: vi.fn(), token: 'patient-a' }))
vi.mock('@tarojs/taro', () => ({ default: { getStorageSync: (k: string) => m.storage.get(k), setStorageSync: (k: string, v: unknown) => m.storage.set(k, v), getFileInfo: m.info,
  getFileSystemManager: () => ({ removeSavedFile: m.remove, unlink: m.remove, getSavedFileList: (o: any) => o.success({ fileList: [{ size: 100 * 1024 * 1024 }] }) }) } }))
vi.mock('../../auth/token', () => ({ getPatientAppToken: () => m.token }))
vi.mock('../../demo/session', () => ({ isDemoSession: () => false }))
vi.mock('../../demo/patientAppData', () => ({ fetchPatientHomeData: vi.fn() }))
vi.mock('../../api/client', () => ({ request: m.request }))
vi.mock('./directUpload', () => ({ uploadDirectVideo: m.upload }))
vi.mock('./api', () => ({ createVideoSession: m.legacy, uploadVideoSegment: m.legacy, finalizeVideoSession: m.legacy, getVideoSessionStatus: m.legacy }))
import { checkCountedStorage, countedSessions, protectedCountedPaths, storeCountedSession, syncCountedQueue, stopCountedRetry, type CountedSession } from './countedSession'
const grant = { video_id: 12, status: 'recording', upload_url: 'https://upload.example.test', upload_token: 'short-lived', object_key: 'server-key.mp4' }
const fixture = (persistence = 'saved') => ({ id: 'session', owner: 1, actionId: 1, actionName: '训练', plannedSets: 3, repetitions: 10, countUnit: 'total' as const,
  startedAt: '2026-09-23T10:00:00Z', trainingDate: '2026-09-23', attempts: [{ id: 'attempt', index: 1, startedAt: '2026-09-23T10:00:00Z', endedAt: '2026-09-23T10:05:00Z', completed: true,
    uploadId: 'upload', uploadMode: 'direct' as const, completionReason: 'time_limit' as const, video: { path: 'whole.mp4', durationMs: 300000, sizeBytes: 100 * 1024 * 1024, persistence: persistence as 'saved' | 'temporary' } }] })
beforeEach(() => {
  vi.clearAllMocks(); m.storage.clear(); m.token = 'patient-a'; stopCountedRetry()
  m.info.mockResolvedValue({ size: 100 * 1024 * 1024 }); m.upload.mockResolvedValue(undefined)
  m.remove.mockImplementation(o => o.success())
  m.request.mockImplementation(async path => path.includes('/recover/') ? { id: 1 } : grant)
})
it('100 MB 新组不走分片，云端尚未确认时保留完整文件', async () => {
  storeCountedSession(fixture()); await checkCountedStorage(); await syncCountedQueue(1)
  expect(m.legacy).not.toHaveBeenCalled(); expect(m.upload).toHaveBeenCalledTimes(1)
  expect(m.upload.mock.calls[0][0].file).toMatchObject({ path: 'whole.mp4', sizeBytes: 100 * 1024 * 1024 })
  expect(m.request.mock.calls[0][1].data.completed_sets[0].completion_reason).toBe('time_limit')
  expect(countedSessions(1)[0].attempts[0].uploaded).not.toBe(true)
  expect(m.remove).not.toHaveBeenCalled(); expect(protectedCountedPaths().has('whole.mp4')).toBe(true)
})
it('云端已成功而响应丢失，重启后即使本地文件丢失也可完成核验', async () => {
  storeCountedSession(fixture()); await syncCountedQueue(1)
  m.upload.mockClear(); m.info.mockRejectedValue(new Error('gone'))
  m.request.mockImplementation(async path => path.includes('/recover/') ? { id: 1 } : { video_id: 12, status: 'attached' })
  await syncCountedQueue(1)
  expect(m.upload).not.toHaveBeenCalled(); expect(countedSessions(1)[0].attempts[0].uploaded).toBe(true)
})
it('临时文件直传确认后先登记再删除；清理失败留路径供下次重试', async () => {
  storeCountedSession(fixture('temporary'))
  m.request.mockImplementation(async path => path.includes('/recover/') ? { id: 1 } : path.includes('/complete/') && m.upload.mock.calls.length ? { video_id: 12, status: 'attached' } : grant)
  m.remove.mockImplementation(o => { expect(countedSessions(1)[0].attempts[0].uploaded).toBe(true); o.fail() })
  await syncCountedQueue(1)
  expect(countedSessions(1)[0].attempts[0].video?.path).toBe('whole.mp4')
  m.remove.mockImplementation(o => o.success()); m.upload.mockClear()
  await syncCountedQueue(1)
  expect(countedSessions(1)[0].attempts[0].video).toBeUndefined(); expect(m.upload).not.toHaveBeenCalled()
})
it('云端已确认而本地文件已消失时清除残留路径，后续调度不再清理', async () => {
  const session: CountedSession = fixture()
  session.attempts[0].uploaded = true
  storeCountedSession(session)
  m.remove.mockImplementation(o => o.fail({ errMsg: 'removeSavedFile:fail ENOENT: no such file' }))
  await syncCountedQueue(1)
  expect(countedSessions(1)[0].attempts[0].video).toBeUndefined()
  expect(m.remove).toHaveBeenCalledTimes(1)
  await syncCountedQueue(1)
  expect(m.remove).toHaveBeenCalledTimes(1)
  expect(m.upload).not.toHaveBeenCalled()
})
it('上传过程中换账号不写完成状态，也不删除原账号视频', async () => {
  storeCountedSession(fixture()); m.upload.mockImplementation(async () => { m.token = 'patient-b' })
  await syncCountedQueue(1)
  expect(countedSessions(1)[0].attempts[0].uploaded).not.toBe(true); expect(m.remove).not.toHaveBeenCalled()
  expect(m.request.mock.calls.filter(([p]) => p.includes('/complete/'))).toHaveLength(1)
})
it('云端未收到且临时文件失效时明确阻止反复无效上传', async () => {
  storeCountedSession(fixture('temporary')); m.info.mockRejectedValue(new Error('gone'))
  await syncCountedQueue(1)
  expect(m.upload).not.toHaveBeenCalled(); expect(countedSessions(1)[0].attempts[0].error).toContain('本地录像文件已丢失')
})
it.each(['expired', 'failed'])('离线积压使旧授权记录 %s 后换对象重试，原组身份不变', async status => {
  storeCountedSession(fixture()); await syncCountedQueue(1)
  m.upload.mockClear(); m.request.mockClear()
  m.request.mockImplementation(async path => path.includes('/recover/') ? { id: 1 } : path.includes('/12/complete/') ? { video_id: 12, status } : { ...grant, video_id: 13 })
  await syncCountedQueue(1)
  expect(m.upload).toHaveBeenCalledTimes(1)
  const data = m.request.mock.calls.find(([path]) => path === '/patient-app/training-video-direct-uploads/')![1].data
  expect(data.client_session_id).not.toBe('upload'); expect(data.motion_attempt_id).toBe('attempt')
  expect(countedSessions(1)[0].attempts[0].videoId).toBe(13)
})
it('三组整文件与旧分片混合队列串行补传，不触碰另一患者', async () => {
  const base = fixture()
  const first = base.attempts[0]
  const queued = { ...base, plannedSets: 4, attempts: [1, 2, 3].map(index => ({ ...first, id: `attempt-${index}`, uploadId: `upload-${index}`, index, video: { ...first.video, path: `whole-${index}.mp4` } })) }
  storeCountedSession(queued)
  const { uploadMode: _mode, video: _video, ...legacy } = first
  const mixed = countedSessions(1)[0]
  mixed.attempts.push({ ...legacy, id: 'legacy', index: 4, videoId: 99, segments: [{ path: 'old-part.mp4', durationMs: 300000, sizeBytes: 100 }] })
  storeCountedSession(mixed); storeCountedSession({ ...fixture(), owner: 2, id: 'other-patient' })
  const uploaded = new Set<number>()
  let concurrent = 0, maxConcurrent = 0
  m.upload.mockImplementation(async ({ grant: current }) => {
    concurrent++; maxConcurrent = Math.max(maxConcurrent, concurrent)
    await Promise.resolve(); uploaded.add(current.video_id); concurrent--
  })
  m.legacy.mockResolvedValue({ video_id: 99, status: 'attached' })
  m.request.mockImplementation(async (path, options) => {
    if (path.includes('/recover/')) return { id: 1 }
    if (!path.includes('/complete/')) return { ...grant, video_id: Number(options.data.motion_attempt_id.split('-').at(-1)) }
    const id = Number(path.match(/\/(\d+)\/complete\//)[1])
    return { video_id: id, status: uploaded.has(id) ? 'attached' : 'recording' }
  })
  await syncCountedQueue(1)
  expect(m.upload).toHaveBeenCalledTimes(3); expect(maxConcurrent).toBe(1)
  expect(m.legacy).toHaveBeenCalledTimes(1)
  expect(countedSessions(1)[0].attempts.every(a => a.uploaded)).toBe(true)
  expect(countedSessions(2)[0].attempts[0].uploaded).not.toBe(true)
})
