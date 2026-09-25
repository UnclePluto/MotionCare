import { expect, it, vi } from 'vitest'
import { saveManagedMotionTrainingFile, releaseManagedMotionTrainingFile } from './managedFile'

it('recovers a moved path across module reload after the session checkpoint fails', async () => {
  const entries = new Map<string, unknown>()
  const storage = { getStorageSync: (key: string) => entries.get(key), setStorageSync: (key: string, value: unknown) => { entries.set(key, value) }, removeStorageSync: (key: string) => { entries.delete(key) } }
  const save = vi.fn(async () => ({ savedFilePath: 'wxfile://store/restart' }))
  await expect(saveManagedMotionTrainingFile('wxfile://temp/restart', save, () => { throw new Error('checkpoint') }, storage)).rejects.toThrow('checkpoint')
  vi.resetModules()
  const restored = await import('./managedFile')
  expect(await restored.saveManagedMotionTrainingFile('wxfile://temp/restart', save, vi.fn(), storage)).toBe('wxfile://store/restart')
  expect(save).toHaveBeenCalledTimes(1)
})

it('times out a save but still checkpoints its late native result', async () => {
  vi.useFakeTimers()
  try {
    let finish!: (value: unknown) => void
    const save = vi.fn(() => new Promise<unknown>(resolve => { finish = resolve }))
    const checkpoint = vi.fn()
    const pending = saveManagedMotionTrainingFile('wxfile://temp/late-save', save, checkpoint)
    const checked = expect(pending).rejects.toThrow('超时')
    await vi.advanceTimersByTimeAsync(10000)
    await checked
    finish({ savedFilePath: 'wxfile://store/late-save' })
    await vi.advanceTimersByTimeAsync(0)
    expect(checkpoint).toHaveBeenCalledWith('wxfile://store/late-save')
  } finally { vi.useRealTimers() }
})

it('retries the new path after a failed checkpoint without moving the old file twice', async () => {
  const saveFile = vi.fn(async () => ({ savedFilePath: 'wxfile://store/one' }))
  const checkpoint = vi.fn().mockImplementationOnce(() => { throw new Error('storage') })
  await expect(saveManagedMotionTrainingFile('wxfile://temp/one', saveFile, checkpoint)).rejects.toThrow('storage')
  expect(await saveManagedMotionTrainingFile('wxfile://temp/one', saveFile, checkpoint)).toBe('wxfile://store/one')
  expect(saveFile).toHaveBeenCalledTimes(1)
  expect(checkpoint).toHaveBeenLastCalledWith('wxfile://store/one')
})

it('checkpoints a permission-denied temporary file before deleting the managed file', async () => {
  const steps: string[] = []
  const fs = { unlink: vi.fn(o => o.fail({ errMsg: 'unlink:fail permission denied' })),
    access: vi.fn(o => o.success()), removeSavedFile: vi.fn(o => { steps.push('delete'); o.success() }) }
  const result = await releaseManagedMotionTrainingFile({ filePath: 'wxfile://temp/two', localFileState: 'temporary',
    onMoved: path => { expect(path).toBe('wxfile://store/two'); steps.push('checkpoint') }
  }, () => fs, async () => { steps.push('save'); return { savedFilePath: 'wxfile://store/two' } })
  expect(result).toEqual({ removed: true, filePath: 'wxfile://store/two' })
  expect(steps).toEqual(['save', 'checkpoint', 'delete'])
})

it('does not delete after a failed checkpoint or resave a saved file', async () => {
  const fs = { unlink: vi.fn(o => o.fail({ errMsg: 'permission denied' })), removeSavedFile: vi.fn(o => o.fail({ errMsg: 'permission denied' })) }
  const save = vi.fn(async () => ({ savedFilePath: 'wxfile://store/three' }))
  await expect(releaseManagedMotionTrainingFile({ filePath: 'wxfile://temp/three', localFileState: 'temporary', onMoved: () => { throw new Error('checkpoint') } }, () => fs, save)).rejects.toThrow('checkpoint')
  expect(fs.removeSavedFile).not.toHaveBeenCalled()
  expect((await releaseManagedMotionTrainingFile({ filePath: 'wxfile://store/four', localFileState: 'saved', onMoved: vi.fn() }, () => fs, save)).removed).toBe(false)
  expect(save).toHaveBeenCalledTimes(1)
})
