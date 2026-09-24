import { afterEach, describe, expect, it, vi } from 'vitest'
import type { CameraContext } from './recorder'
import { CountedTrainingRecorder } from './countedRecorder'

afterEach(() => vi.useRealTimers())

function setup(autoStart = true) {
  vi.useFakeTimers()
  vi.setSystemTime(0)
  const starts: Parameters<CameraContext['startRecord']>[0][] = []
  const stops: Parameters<CameraContext['stopRecord']>[0][] = []
  const camera: CameraContext = {
    startRecord: vi.fn(options => { starts.push(options); if (autoStart) options.success?.() }),
    stopRecord: vi.fn(options => { stops.push(options) })
  }
  const onSegment = vi.fn(async (): Promise<void> => undefined)
  const onFatalError = vi.fn()
  const onStopped = vi.fn()
  const onStopSlow = vi.fn()
  const recorder = new CountedTrainingRecorder({ camera, now: Date.now, onSegment, onFatalError, onStopped, onStopSlow })
  return { recorder, camera, starts, stops, onSegment, onFatalError, onStopped, onStopSlow }
}

describe('计数组录像的串行收尾', () => {
  it('本地分段先于微信兜底，完成本组复用在途停止且只保存一次', async () => {
    const { recorder, starts, stops, onSegment, onStopped } = setup()
    await recorder.start()
    await vi.advanceTimersByTimeAsync(5000)
    expect(stops).toHaveLength(1)
    expect(starts[0].timeout! * 1000).toBeGreaterThan(5000)
    const finished = recorder.finish()
    expect(stops).toHaveLength(1)
    stops[0].success?.({ tempVideoPath: 'tail.mp4' })
    starts[0].timeoutCallback?.({ tempVideoPath: 'tail.mp4' })
    expect(await finished).toEqual([{ savedFilePath: 'tail.mp4', durationMs: 5000 }])
    await vi.advanceTimersByTimeAsync(1000)
    expect(starts).toHaveLength(1)
    expect(onSegment).toHaveBeenCalledTimes(1)
    expect(onStopped).toHaveBeenCalledWith(5000)
  })

  it('点击完成立即发起一次停止，慢回调仍能保存，等待耗时不算运动时长', async () => {
    const { recorder, stops, onStopSlow, onFatalError, onStopped } = setup()
    await recorder.start()
    await vi.advanceTimersByTimeAsync(2000)
    const finished = recorder.finish()
    expect(stops).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(12000)
    const retry = recorder.finish()
    expect(stops).toHaveLength(1)
    expect(onStopSlow).toHaveBeenCalledWith('stopping')
    expect(onFatalError).not.toHaveBeenCalled()
    stops[0].success?.({ tempVideoPath: 'slow-tail.mp4' })
    expect(await finished).toEqual([{ savedFilePath: 'slow-tail.mp4', durationMs: 2000 }])
    expect(await retry).toEqual(await finished)
    expect(onStopped).toHaveBeenCalledTimes(1)
  })

  it('尾段永久无回调时有最终期限，重试不假报完成且迟到结果不能复活本组', async () => {
    const { recorder, stops, starts, onFatalError, onSegment } = setup()
    await recorder.start()
    await vi.advanceTimersByTimeAsync(5000)
    const finished = recorder.finish().catch(error => error)
    await vi.advanceTimersByTimeAsync(30000)
    expect(onFatalError).toHaveBeenCalledTimes(1)
    expect(await finished).toEqual(expect.objectContaining({ message: expect.stringContaining('重做本组') }))
    await expect(recorder.finish()).rejects.toThrow('重做本组')
    await expect(recorder.start()).rejects.toThrow('重做本组')
    stops[0].success?.({ tempVideoPath: 'late.mp4' })
    starts[0].timeoutCallback?.({ tempVideoPath: 'late.mp4' })
    await vi.advanceTimersByTimeAsync(1000)
    expect(onSegment).not.toHaveBeenCalled()
    expect(starts).toHaveLength(1)
    expect(stops).toHaveLength(1)
  })

  it('启动确认缺失时也会结束等待，取消后迟到启动不能触发续录', async () => {
    const { recorder, starts, stops, onFatalError } = setup(false)
    const started = recorder.start().catch(error => error)
    await vi.advanceTimersByTimeAsync(30000)
    expect(onFatalError).toHaveBeenCalledTimes(1)
    expect(await started).toEqual(expect.objectContaining({ message: expect.stringContaining('重做本组') }))
    recorder.discard()
    starts[0].success?.()
    await vi.advanceTimersByTimeAsync(60000)
    expect(starts).toHaveLength(1)
    expect(stops).toHaveLength(0)
  })

  it('上一段视频安全交付后才续录，启动延迟不计入本段时长', async () => {
    const { recorder, starts, stops, onSegment } = setup(false)
    let save!: () => void
    onSegment.mockImplementationOnce(() => new Promise<void>(resolve => { save = resolve }))
    const started = recorder.start()
    await vi.advanceTimersByTimeAsync(1700)
    starts[0].success?.(); await started
    await vi.advanceTimersByTimeAsync(5000)
    expect(stops).toHaveLength(1)
    stops[0].success?.({ tempVideoPath: 'first.mp4' })
    await vi.advanceTimersByTimeAsync(1000)
    expect(starts).toHaveLength(1)
    save()
    await vi.advanceTimersByTimeAsync(1)
    expect(starts).toHaveLength(2)
    expect(onSegment).toHaveBeenCalledWith('first.mp4', 5000)
    recorder.discard()
  })

  it('保存尾段失败可重试原文件，不能重新停止或漏掉尾段', async () => {
    const { recorder, stops, onSegment } = setup()
    onSegment.mockRejectedValueOnce(new Error('文件保存失败'))
    await recorder.start()
    await vi.advanceTimersByTimeAsync(1000)
    const finished = recorder.finish().catch(error => error)
    expect(stops).toHaveLength(1)
    stops[0].success?.({ tempVideoPath: 'tail.mp4' })
    expect(await finished).toEqual(expect.objectContaining({ message: '文件保存失败' }))
    expect(recorder.hasFailedSegment()).toBe(true)
    await recorder.retryFailedSegment()
    expect(await recorder.finish()).toEqual([{ savedFilePath: 'tail.mp4', durationMs: 1000 }])
    expect(stops).toHaveLength(1)
    expect(recorder.hasFailedSegment()).toBe(false)
  })

  it('取消在途停止后旧回调不保存、不续录', async () => {
    const { recorder, starts, stops, onSegment } = setup()
    await recorder.start()
    const finished = recorder.finish().catch(error => error)
    recorder.discard()
    expect(await finished).toBeInstanceOf(Error)
    stops[0]?.success?.({ tempVideoPath: 'discarded.mp4' })
    starts[0].timeoutCallback?.({ tempVideoPath: 'discarded.mp4' })
    await vi.advanceTimersByTimeAsync(60000)
    expect(onSegment).not.toHaveBeenCalled()
    expect(starts).toHaveLength(1)
  })

  it('文件保存仍在等待时取消也立即结束完成操作', async () => {
    const { recorder, stops, onSegment } = setup()
    let save!: () => void
    onSegment.mockImplementationOnce(() => new Promise<void>(resolve => { save = resolve }))
    await recorder.start()
    const finished = recorder.finish().catch(error => error)
    stops[0].success?.({ tempVideoPath: 'pending-save.mp4' })
    await vi.advanceTimersByTimeAsync(1)
    recorder.discard()
    expect(await finished).toEqual(expect.objectContaining({ message: expect.stringContaining('取消') }))
    save()
    await vi.advanceTimersByTimeAsync(1000)
    await expect(recorder.finish()).rejects.toThrow('取消')
  })

  it('兜底自动返回视频会撤销本地分段定时器，完成时不重复停止已结束片段', async () => {
    const { recorder, starts, stops, onSegment } = setup()
    await recorder.start()
    await vi.advanceTimersByTimeAsync(4500)
    starts[0].timeoutCallback?.({ tempVideoPath: 'native-ended.mp4' })
    const result = await recorder.finish()
    await vi.advanceTimersByTimeAsync(60000)
    expect(result).toEqual([{ savedFilePath: 'native-ended.mp4', durationMs: 4500 }])
    expect(stops).toHaveLength(0)
    expect(starts).toHaveLength(1)
    expect(onSegment).toHaveBeenCalledTimes(1)
  })

  it('达到单组时长边界只触发未完成处理，不额外续录', async () => {
    const { camera, starts, stops, onSegment } = setup()
    const onMaxDuration = vi.fn()
    const recorder = new CountedTrainingRecorder({ camera, now: Date.now, onSegment, maxDurationMs: 7000, onMaxDuration })
    await recorder.start()
    await vi.advanceTimersByTimeAsync(5000)
    stops[0].success?.({ tempVideoPath: 'first.mp4' })
    await vi.advanceTimersByTimeAsync(1)
    expect(starts).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(2000)
    expect(stops).toHaveLength(2)
    stops[1].success?.({ tempVideoPath: 'limit.mp4' })
    await vi.advanceTimersByTimeAsync(60000)
    expect(onMaxDuration).toHaveBeenCalledTimes(1)
    expect(starts).toHaveLength(2)
    expect(onSegment).toHaveBeenLastCalledWith('limit.mp4', 2000)
    recorder.discard()
  })

  it('空视频结果立即失败，后续迟到成功不能假报完成', async () => {
    const { recorder, stops, onFatalError, onSegment } = setup()
    await recorder.start()
    const result = recorder.finish().catch(error => error)
    stops[0].success?.({ tempVideoPath: '' })
    expect(await result).toEqual(expect.objectContaining({ message: expect.stringContaining('未返回有效录像') }))
    stops[0].success?.({ tempVideoPath: 'too-late.mp4' })
    await vi.advanceTimersByTimeAsync(1)
    expect(onFatalError).toHaveBeenCalledTimes(1)
    expect(onSegment).not.toHaveBeenCalled()
  })

  it('分段达到上限时同时点击完成，仍按未完成处理', async () => {
    const { camera, stops, onSegment } = setup()
    const onMaxDuration = vi.fn()
    const recorder = new CountedTrainingRecorder({ camera, now: Date.now, onSegment, maxDurationMs: 5000, onMaxDuration })
    await recorder.start()
    await vi.advanceTimersByTimeAsync(5000)
    const result = recorder.finish().catch(error => error)
    stops[0].success?.({ tempVideoPath: 'limit.mp4' })
    expect(await result).toEqual(expect.objectContaining({ message: expect.stringContaining('时限') }))
    expect(onMaxDuration).toHaveBeenCalledTimes(1)
    await expect(recorder.finish()).rejects.toThrow('时限')
  })

  it('原文件保存重试悬挂时，重做也会结束旧重试任务', async () => {
    const { recorder, stops, onSegment } = setup()
    onSegment.mockRejectedValueOnce(new Error('保存失败'))
    await recorder.start()
    const result = recorder.finish().catch(error => error)
    stops[0].success?.({ tempVideoPath: 'retry.mp4' })
    await result
    let save!: () => void
    onSegment.mockImplementationOnce(() => new Promise<void>(resolve => { save = resolve }))
    let settled = false
    const retry = recorder.retryFailedSegment().catch(error => error).finally(() => { settled = true })
    await vi.advanceTimersByTimeAsync(1)
    recorder.discard()
    await vi.advanceTimersByTimeAsync(1)
    expect(settled).toBe(true)
    expect(await retry).toBeInstanceOf(Error)
    save()
  })
})
