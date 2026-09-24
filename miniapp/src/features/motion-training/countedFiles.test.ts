import { beforeEach, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ save: vi.fn(), info: vi.fn(), remove: vi.fn(), unlink: vi.fn() }))
vi.mock('@tarojs/taro', () => ({ default: { saveFile: mocks.save, getFileInfo: mocks.info, getFileSystemManager: () => ({ removeSavedFile: mocks.remove, unlink: mocks.unlink }) } }))
import { createCountedFilePreparer, releaseCountedFile } from './countedFiles'
beforeEach(() => { vi.resetAllMocks(); mocks.save.mockResolvedValue({ savedFilePath: 'saved.mp4' }); mocks.info.mockResolvedValue({ size: 100 * 1024 * 1024 }) })
it('持久化成功但元数据失败后重试已保存路径，不重复移动临时文件', async () => {
  const prepare = createCountedFilePreparer()
  mocks.info.mockRejectedValueOnce(new Error('busy'))
  await expect(prepare('temp.mp4', 10000)).rejects.toThrow()
  expect(await prepare('temp.mp4', 10000)).toMatchObject({ path: 'saved.mp4', persistence: 'saved', durationMs: 10000 })
  expect(mocks.save).toHaveBeenCalledTimes(1)
  expect(mocks.info).toHaveBeenLastCalledWith({ filePath: 'saved.mp4' })
})
it('持久化空间不足时保留可读临时文件直接上传', async () => {
  mocks.save.mockRejectedValue(new Error('no space'))
  expect(await createCountedFilePreparer()('temp.mp4', 300000)).toMatchObject({ path: 'temp.mp4', persistence: 'temporary', sizeBytes: 100 * 1024 * 1024 })
})
it('临时文件不可读不能虚报保存成功', async () => {
  mocks.save.mockRejectedValue(new Error('no space')); mocks.info.mockRejectedValue(new Error('not found'))
  await expect(createCountedFilePreparer()('temp.mp4', 300000)).rejects.toThrow()
})
it.each(['saved', 'temporary'] as const)('按文件类型 %s 清理，删除失败返回 false 供队列保留路径', async persistence => {
  const remove = persistence === 'saved' ? mocks.remove : mocks.unlink
  remove.mockImplementation(o => o.fail())
  expect(await releaseCountedFile({ path: 'video.mp4', persistence })).toBe(false)
  remove.mockImplementation(o => o.success())
  expect(await releaseCountedFile({ path: 'video.mp4', persistence })).toBe(true)
})
it.each(['saved', 'temporary'] as const)('%s 文件已不存在时视为已清理，其它删除错误仍需重试', async persistence => {
  const remove = persistence === 'saved' ? mocks.remove : mocks.unlink
  const file = { path: 'video.mp4', persistence }
  remove.mockImplementation(o => o.fail({ errMsg: 'removeSavedFile:fail file not exist' }))
  expect(await releaseCountedFile(file)).toBe(true)
  remove.mockImplementation(o => o.fail({ errMsg: 'removeSavedFile:fail permission denied' }))
  expect(await releaseCountedFile(file)).toBe(false)
})
