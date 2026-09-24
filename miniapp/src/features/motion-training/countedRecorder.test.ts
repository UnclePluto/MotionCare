import { afterEach, expect, it, vi } from 'vitest'
import { CountedTrainingRecorder } from './countedRecorder'
import type { CameraContext } from './recorder'
afterEach(() => vi.useRealTimers())
function setup(autoStart = true) {
  vi.useFakeTimers(); vi.setSystemTime(0)
  let start!: Parameters<CameraContext['startRecord']>[0]
  let stop!: Parameters<CameraContext['stopRecord']>[0]
  const camera: CameraContext = { startRecord: vi.fn(o => { start = o; if (autoStart) o.success?.() }), stopRecord: vi.fn(o => { stop = o }) }
  const onVideo = vi.fn(async (): Promise<void> => undefined), onEnding = vi.fn(), onFatalError = vi.fn(), onStopSlow = vi.fn()
  const recorder = new CountedTrainingRecorder({ camera, now: Date.now, onVideo, onEnding, onFatalError, onStopSlow } as any)
  return { recorder, camera, onVideo, onEnding, onFatalError, onStopSlow, start: () => start, stop: () => stop }
}
it('接近五分钟仍只启动一次，手动结束只交付一个完整文件', async () => {
  const t = setup(); await t.recorder.start(); await vi.advanceTimersByTimeAsync(299000)
  expect(t.camera.startRecord).toHaveBeenCalledTimes(1); expect(t.camera.stopRecord).not.toHaveBeenCalled()
  const result = t.recorder.finish('manual')
  expect(t.onEnding).toHaveBeenCalledWith(299000, 'manual')
  t.stop().success?.({ tempVideoPath: 'whole.mp4' }); t.start().timeoutCallback?.({ tempVideoPath: 'whole.mp4' })
  expect(await result).toEqual({ path: 'whole.mp4', durationMs: 299000 })
  expect(t.onVideo).toHaveBeenCalledTimes(1); expect(t.camera.stopRecord).toHaveBeenCalledTimes(1)
})
it('到五分钟只进入休息等待SDK停止结果，不再次停止或续录', async () => {
  const t = setup(); await t.recorder.start(); expect(t.start().timeout).toBe(300)
  await vi.advanceTimersByTimeAsync(300000)
  expect(t.onEnding).toHaveBeenCalledWith(300000, 'time_limit')
  const result = t.recorder.finish('manual'); expect(t.camera.stopRecord).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(2000); t.start().timeoutCallback?.({ tempVideoPath: 'limit.mp4' })
  expect(await result).toEqual({ path: 'limit.mp4', durationMs: 300000 })
  expect(t.onEnding).toHaveBeenCalledTimes(1); expect(t.camera.startRecord).toHaveBeenCalledTimes(1)
})
it('SDK期限回调先到也只触发一次结束，不丢失文件', async () => {
  const t = setup(); await t.recorder.start(); vi.setSystemTime(300000)
  t.start().timeoutCallback?.({ tempVideoPath: 'sdk-first.mp4' })
  await expect(t.recorder.finish('time_limit')).resolves.toMatchObject({ path: 'sdk-first.mp4' })
  await vi.advanceTimersByTimeAsync(300000)
  expect(t.onEnding).toHaveBeenCalledTimes(1); expect(t.camera.stopRecord).not.toHaveBeenCalled()
})
it('完成操作重入不会重复停止或把等待算为运动', async () => {
  const t = setup(); await t.recorder.start(); await vi.advanceTimersByTimeAsync(2000)
  const first = t.recorder.finish('manual'); await vi.advanceTimersByTimeAsync(12000)
  const second = t.recorder.finish('manual'); expect(t.onStopSlow).toHaveBeenCalled()
  t.stop().success?.({ tempVideoPath: 'slow.mp4' })
  expect(await first).toEqual({ path: 'slow.mp4', durationMs: 2000 }); expect(await second).toEqual(await first)
  expect(t.camera.stopRecord).toHaveBeenCalledTimes(1)
})
it('结束后缺失回调会终止等待，迟到文件不能复活', async () => {
  const t = setup(); await t.recorder.start(); const result = t.recorder.finish('manual').catch(e => e)
  await vi.advanceTimersByTimeAsync(30000); expect(await result).toBeInstanceOf(Error)
  expect(t.onFatalError).toHaveBeenCalledTimes(1); t.stop().success?.({ tempVideoPath: 'late.mp4' })
  await expect(t.recorder.finish('manual')).rejects.toThrow('重做'); expect(t.onVideo).not.toHaveBeenCalled()
})
it('启动缺失有期限，迟到启动不能进入录制', async () => {
  const t = setup(false); const start = t.recorder.start().catch(e => e)
  await vi.advanceTimersByTimeAsync(30000); expect(await start).toBeInstanceOf(Error)
  t.start().success?.(); await vi.advanceTimersByTimeAsync(300000); expect(t.onEnding).not.toHaveBeenCalled()
})
it('未到上限的原生异常结束不能当作完成组', async () => {
  const t = setup(); await t.recorder.start(); await vi.advanceTimersByTimeAsync(10000)
  t.start().timeoutCallback?.({ tempVideoPath: 'interrupted.mp4' })
  expect(t.onFatalError).toHaveBeenCalledTimes(1); expect(t.onVideo).not.toHaveBeenCalled()
})
it('完整文件交付失败后重试同一文件，不重新停止', async () => {
  const t = setup(); t.onVideo.mockRejectedValueOnce(new Error('读取文件失败'))
  await t.recorder.start(); await vi.advanceTimersByTimeAsync(5000)
  const result = t.recorder.finish('manual').catch(e => e); t.stop().success?.({ tempVideoPath: 'whole.mp4' })
  expect(await result).toBeInstanceOf(Error); expect(t.recorder.hasFailedVideo()).toBe(true)
  await t.recorder.retryVideo(); expect(await t.recorder.finish('manual')).toMatchObject({ path: 'whole.mp4' })
  expect(t.camera.stopRecord).toHaveBeenCalledTimes(1)
})
it('取消挂起的文件保存立即结束旧任务', async () => {
  const t = setup(); t.onVideo.mockImplementation(() => new Promise(() => {})); await t.recorder.start()
  const result = t.recorder.finish('manual').catch(e => e); t.stop().success?.({ tempVideoPath: 'whole.mp4' })
  await vi.advanceTimersByTimeAsync(1); t.recorder.discard(); expect(await result).toBeInstanceOf(Error)
  expect(t.camera.stopRecord).toHaveBeenCalledTimes(1)
})
it('在启动确认前请求完成会等待确认再只停止一次', async () => {
  const t = setup(false); const started = t.recorder.start(); const finished = t.recorder.finish('manual')
  expect(t.camera.stopRecord).not.toHaveBeenCalled(); t.start().success?.(); await started
  t.stop().success?.({ tempVideoPath: 'short.mp4' }); await finished; expect(t.camera.stopRecord).toHaveBeenCalledTimes(1)
})
