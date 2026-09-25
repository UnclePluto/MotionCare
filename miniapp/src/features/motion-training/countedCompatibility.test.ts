import { beforeEach, expect, it, vi } from 'vitest'
const state = vi.hoisted(() => ({ saved: undefined as unknown }))
vi.mock('@tarojs/taro', () => ({ default: { getStorageSync: () => state.saved } }))
vi.mock('../../auth/token', () => ({ getPatientAppToken: () => 'test-token' }))
vi.mock('../../demo/session', () => ({ isDemoSession: () => false }))
vi.mock('../../demo/patientAppData', () => ({ fetchPatientHomeData: vi.fn() }))
vi.mock('../../api/client', () => ({ request: vi.fn() }))
import { protectedCountedPaths } from './countedSession'
import { cleanupAndCheckMotionTrainingStorage } from './storageGuard'
beforeEach(() => { state.saved = undefined })
it('高抬腿启动时保护同机已有的整段和分片待上传录像，不因 segments 缺失崩溃或删除视频', async () => {
  state.saved = { 3: [{ attempts: [
    { uploadMode: 'direct', completed: true, video: { path: 'whole.mp4', persistence: 'saved' } },
    { completed: true, segments: [{ path: 'segment.mp4' }] }
  ] }] }
  const remove = vi.fn()
  const files = [{ filePath: 'whole.mp4', size: 1000 }, { filePath: 'segment.mp4', size: 1000 }]
  const result = await cleanupAndCheckMotionTrainingStorage({
    protectedPaths: protectedCountedPaths(), hasPendingSession: () => false,
    listSavedFiles: async () => files, removeSavedFile: remove, isActive: () => true
  })
  expect(result.kind).toBe('ready')
  expect(remove).not.toHaveBeenCalled()
})
