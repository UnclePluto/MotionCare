import { afterEach, describe, expect, it, vi } from 'vitest'

import { MotionTrainingRecorder } from './recorder'

afterEach(() => { vi.useRealTimers() })

type StartOptions = {
  success?: () => void
  fail?: () => void
  timeout?: number
  timeoutCallback?: (result: { tempVideoPath: string }) => void
}

type StopOptions = {
  success?: (result: { tempVideoPath: string }) => void
  fail?: () => void
}

function fakeCamera() {
  const startOptions: StartOptions[] = []
  const stopOptions: StopOptions[] = []
  return {
    camera: {
      startRecord: vi.fn((options: StartOptions) => {
        startOptions.push(options)
        options.success?.()
      }),
      stopRecord: vi.fn((options: StopOptions) => {
        stopOptions.push(options)
      })
    },
    startOptions,
    stopOptions
  }
}

async function flushPromises(times = 30) {
  for (let index = 0; index < times; index += 1) {
    await Promise.resolve()
  }
}

describe('MotionTrainingRecorder', () => {
  it('keeps finish blocked after pause reports a failed metadata write until the original segment is retried', async () => {
    const { camera, startOptions } = fakeCamera()
    let failMetadata!: (error: Error) => void
    let now = 0
    const onSegment = vi.fn().mockResolvedValueOnce(undefined).mockImplementationOnce(() => new Promise((_resolve, reject) => { failMetadata = reject })).mockResolvedValue(undefined)
    const recorder = new MotionTrainingRecorder({ camera, now: () => now, onSegment })
    await recorder.start()
    now = 60000
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://temp/first.mp4' })
    await flushPromises()
    now = 120000
    startOptions[1].timeoutCallback?.({ tempVideoPath: 'wxfile://temp/second.mp4' })
    await flushPromises()
    const pauseResult = recorder.pause().catch(error => error)
    failMetadata(new Error('storage full'))
    expect(await pauseResult).toBeInstanceOf(Error)
    await expect(recorder.finish()).rejects.toThrow()
    await expect(recorder.start()).rejects.toThrow()
    expect(camera.startRecord).toHaveBeenCalledTimes(2)
    await recorder.retryFailedSegment()
    expect(await recorder.finish()).toHaveLength(2)
  })
  it('records thirty minute-long clips and never starts clip thirty-one', async () => {
    const { camera, startOptions } = fakeCamera()
    let now = 0
    const recorder = new MotionTrainingRecorder({ camera, now: () => now, maxDurationMs: 1800000, onSegment: async () => {} })
    await recorder.start()
    for (let index = 0; index < 30; index += 1) {
      expect(startOptions[index].timeout).toBe(60)
      now += 60000
      startOptions[index].timeoutCallback?.({ tempVideoPath: `wxfile://temp/minute-${index}.mp4` })
      await flushPromises(30)
    }
    expect(camera.startRecord).toHaveBeenCalledTimes(30)
    expect(await recorder.finish()).toHaveLength(30)
  })

  it('waits for segment metadata before admitting the next recording and pauses if space is insufficient', async () => {
    const { camera, startOptions } = fakeCamera()
    let release!: () => void
    const pending = new Promise<void>(resolve => { release = resolve })
    const onPause = vi.fn()
    let canContinue = true
    const recorder = new MotionTrainingRecorder({ camera, now: () => 60000, onSegment: () => pending, canContinueRecording: () => canContinue, onPause })
    await recorder.start()
    canContinue = false
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://temp/full.mp4' })
    await flushPromises(30)
    expect(camera.startRecord).toHaveBeenCalledTimes(1)
    release()
    await flushPromises(30)
    expect(camera.startRecord).toHaveBeenCalledTimes(1)
    expect(camera.stopRecord).not.toHaveBeenCalled()
    expect(onPause).toHaveBeenCalledTimes(1)
    expect(await recorder.finish()).toHaveLength(1)
  })

  it('does not complete pause or allow resume until pending metadata passes the buffer check', async () => {
    const { camera, startOptions } = fakeCamera()
    let release!: () => void
    const metadata = new Promise<void>(resolve => { release = resolve })
    let allowed = true
    const recorder = new MotionTrainingRecorder({ camera, now: () => 60000, onSegment: () => metadata, canContinueRecording: () => allowed })
    await recorder.start()
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://temp/pending.mp4' })
    let paused = false
    const pausing = recorder.pause().then(() => { paused = true })
    await flushPromises()
    expect(paused).toBe(false)
    allowed = false
    release()
    await pausing
    await expect(recorder.start()).rejects.toThrow('等待')
    expect(camera.startRecord).toHaveBeenCalledTimes(1)
    allowed = true
    await recorder.start()
    expect(camera.startRecord).toHaveBeenCalledTimes(2)
  })

  it('does not restart if finish arrives while segment metadata is pending', async () => {
    const { camera, startOptions } = fakeCamera()
    let release!: () => void
    const pending = new Promise<void>(resolve => { release = resolve })
    const recorder = new MotionTrainingRecorder({ camera, now: () => 60000, onSegment: () => pending, canContinueRecording: () => true })
    await recorder.start()
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://temp/full.mp4' })
    const finishing = recorder.finish()
    release()
    expect(await finishing).toHaveLength(1)
    await flushPromises(30)
    expect(camera.startRecord).toHaveBeenCalledTimes(1)
  })
  it('persists timeout metadata before starting the next minute-long recording', async () => {
    const { camera, startOptions } = fakeCamera()
    const order: string[] = []
    let now = 0
    const onSegment = vi.fn(async (path: string, durationMs: number) => {
      order.push(`segment:${path}:${durationMs}`)
    })
    const recorder = new MotionTrainingRecorder({
      camera,
      now: () => now,
      onSegment
    })
    camera.startRecord.mockImplementation((options: StartOptions) => {
      startOptions.push(options)
      order.push('start')
      options.success?.()
    })

    await recorder.start()
    expect(camera.startRecord).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({ timeout: 60 })
    )
    now = 60_000
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://store/segment-0.mp4' })
    await flushPromises()

    expect(camera.startRecord).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ timeout: 60 })
    )
    expect(onSegment).toHaveBeenNthCalledWith(1, 'wxfile://store/segment-0.mp4', 60_000)
    expect(order).toEqual([
      'start',
      'segment:wxfile://store/segment-0.mp4:60000',
      'start'
    ])
  })

  it('pause saves segments at least two seconds long and discards shorter files', async () => {
    const { camera, stopOptions } = fakeCamera()
    let now = 1000
    const delivered: Array<{ path: string; durationMs: number }> = []
    const onPause = vi.fn()
    const recorder = new MotionTrainingRecorder({
      camera,
      now: () => now,
      onPause,
      onSegment: async (path, durationMs) => {
        delivered.push({ path, durationMs })
      }
    })

    await recorder.start()
    now = 3500
    const pausePromise = recorder.pause()
    stopOptions[0].success?.({ tempVideoPath: 'wxfile://store/segment-long.mp4' })
    await pausePromise

    await recorder.start()
    now = 4999
    const shortPausePromise = recorder.pause()
    stopOptions[1].success?.({ tempVideoPath: 'wxfile://store/segment-short.mp4' })
    await shortPausePromise

    expect(delivered).toEqual([{ path: 'wxfile://store/segment-long.mp4', durationMs: 2500 }])
    expect(onPause).toHaveBeenCalledTimes(2)
  })

  it('preserves a short tail when pausing at the training deadline', async () => {
    const { camera, stopOptions } = fakeCamera()
    let now = 1000
    const onSegment = vi.fn().mockResolvedValue(undefined)
    const recorder = new MotionTrainingRecorder({ camera, now: () => now, onSegment })
    await recorder.start()
    now = 1999
    const stopped = recorder.pause({ preserveShortTail: true })
    stopOptions[0].success?.({ tempVideoPath: 'wxfile://temp/deadline-tail.mp4' })
    await stopped
    expect(onSegment).toHaveBeenCalledWith('wxfile://temp/deadline-tail.mp4', 999)
    expect(await recorder.finish()).toHaveLength(1)
  })

  it('delivers the same path only once when timeout and stop success race', async () => {
    const { camera, startOptions, stopOptions } = fakeCamera()
    let now = 0
    const delivered: string[] = []
    const recorder = new MotionTrainingRecorder({
      camera,
      now: () => now,
      onSegment: async (path) => {
        delivered.push(path)
      }
    })

    await recorder.start()
    now = 30000
    const finishPromise = recorder.finish()
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://store/segment-0.mp4' })
    stopOptions[0].success?.({ tempVideoPath: 'wxfile://store/segment-0.mp4' })
    await finishPromise
    await flushPromises()

    expect(delivered).toEqual(['wxfile://store/segment-0.mp4'])
  })

  it('finish stops automatic continuation and returns all delivered segments', async () => {
    const { camera, startOptions, stopOptions } = fakeCamera()
    let now = 0
    const recorder = new MotionTrainingRecorder({
      camera,
      now: () => now,
      onSegment: vi.fn(async () => undefined)
    })

    await recorder.start()
    now = 30000
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://store/segment-0.mp4' })
    await flushPromises()

    now = 42000
    const finishPromise = recorder.finish()
    stopOptions[0].success?.({ tempVideoPath: 'wxfile://store/segment-1.mp4' })
    const segments = await finishPromise

    expect(camera.startRecord).toHaveBeenCalledTimes(2)
    expect(segments).toEqual([
      { savedFilePath: 'wxfile://store/segment-0.mp4', durationMs: 30000 },
      { savedFilePath: 'wxfile://store/segment-1.mp4', durationMs: 12000 }
    ])
  })

  it('keeps the active generation stoppable after the native stop fails', async () => {
    vi.useFakeTimers()
    const { camera, stopOptions } = fakeCamera()
    let now = 1000
    const recorder = new MotionTrainingRecorder({
      camera,
      now: () => now,
      onSegment: vi.fn(async () => undefined)
    })

    await recorder.start()
    now = 4000
    const firstFinish = recorder.finish().catch(error => error)
    stopOptions[0].fail?.()
    await vi.advanceTimersByTimeAsync(10000)
    expect(await firstFinish).toEqual(expect.objectContaining({ message: '录像停止失败，请稍后重试' }))

    now = 5000
    const retriedFinish = recorder.finish()
    expect(camera.stopRecord).toHaveBeenCalledTimes(2)
    stopOptions[1].success?.({ tempVideoPath: 'wxfile://store/retried-stop.mp4' })

    await expect(retriedFinish).resolves.toEqual([
      { savedFilePath: 'wxfile://store/retried-stop.mp4', durationMs: 4000 }
    ])
  })

  it('keeps one timeout tail when finish starts before timeout and native stop fails', async () => {
    const { camera, startOptions, stopOptions } = fakeCamera()
    let now = 0
    const onMaxDuration = vi.fn()
    const onSegment = vi.fn(async () => undefined)
    const recorder = new MotionTrainingRecorder({
      camera,
      now: () => now,
      maxDurationMs: 122_000,
      onMaxDuration,
      onSegment
    })

    await recorder.start()
    now = 60_000
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://temp/segment-0.mp4' })
    await flushPromises()
    expect(camera.startRecord).toHaveBeenCalledTimes(2)
    now = 120_000
    startOptions[1].timeoutCallback?.({ tempVideoPath: 'wxfile://temp/segment-1.mp4' })
    await flushPromises()
    expect(camera.startRecord).toHaveBeenCalledTimes(3)

    now = 121_900
    const firstFinish = recorder.finish()
    const firstFinishResult = firstFinish.catch((error: unknown) => error)
    expect(camera.stopRecord).toHaveBeenCalledTimes(1)

    now = 122_000
    startOptions[2].timeoutCallback?.({ tempVideoPath: 'wxfile://temp/timeout-tail.mp4' })

    expect(onMaxDuration).toHaveBeenCalledWith(122_000)
    expect(camera.stopRecord).toHaveBeenCalledTimes(1)
    await flushPromises()
    expect(onSegment).toHaveBeenNthCalledWith(3, 'wxfile://temp/timeout-tail.mp4', 2_000)

    stopOptions[0].fail?.()
    await expect(firstFinishResult).resolves.toHaveLength(3)

    startOptions[2].timeoutCallback?.({ tempVideoPath: 'wxfile://temp/timeout-tail.mp4' })
    now = 123_000
    const retriedFinish = recorder.finish()
    expect(camera.stopRecord).toHaveBeenCalledTimes(1)

    await expect(retriedFinish).resolves.toEqual([
      { savedFilePath: 'wxfile://temp/segment-0.mp4', durationMs: 60_000 },
      { savedFilePath: 'wxfile://temp/segment-1.mp4', durationMs: 60_000 },
      { savedFilePath: 'wxfile://temp/timeout-tail.mp4', durationMs: 2_000 }
    ])
    expect(onSegment).toHaveBeenCalledTimes(3)
    expect(onMaxDuration).toHaveBeenCalledTimes(1)
  })

  it('uses the remaining duration for generation 30 and never records past the upload contract', async () => {
    const { camera, startOptions } = fakeCamera()
    let now = 0
    const onMaxDuration = vi.fn()
    const recorder = new MotionTrainingRecorder({
      camera,
      now: () => now,
      maxDurationMs: 1_797_000,
      onMaxDuration,
      onSegment: vi.fn(async () => undefined)
    })

    await recorder.start()
    for (let index = 0; index < 29; index += 1) {
      now = (index + 1) * 60_000
      startOptions[index].timeoutCallback?.({ tempVideoPath: `wxfile://store/segment-${index}.mp4` })
      await flushPromises()
    }

    expect(camera.startRecord).toHaveBeenCalledTimes(30)
    expect(startOptions.slice(0, 29).every((options) => options.timeout === 60)).toBe(true)
    expect(startOptions[29].timeout).toBe(57)

    now = 1_797_000
    startOptions[29].timeoutCallback?.({ tempVideoPath: 'wxfile://store/segment-29.mp4' })
    const finishPromise = recorder.finish()
    await flushPromises()

    expect(camera.startRecord).toHaveBeenCalledTimes(30)
    const segments = await finishPromise
    expect(segments).toHaveLength(30)
    expect(segments.reduce((total, segment) => total + segment.durationMs, 0)).toBe(1_797_000)
    expect(onMaxDuration).toHaveBeenCalledTimes(1)
  })

  it('reports the fixed timeout cutoff before the final segment delivery settles', async () => {
    const { camera, startOptions } = fakeCamera()
    let now = 1000
    let releaseSegment!: () => void
    const segmentPending = new Promise<void>((resolve) => {
      releaseSegment = resolve
    })
    const onMaxDuration = vi.fn()
    const recorder = new MotionTrainingRecorder({
      camera,
      now: () => now,
      maxDurationMs: 122_000,
      onMaxDuration,
      onSegment: async path => { if (path.includes('final')) await segmentPending }
    })

    await recorder.start()
    now = 61_000
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://temp/segment-0.mp4' })
    await flushPromises()
    expect(camera.startRecord).toHaveBeenCalledTimes(2)
    now = 121_000
    startOptions[1].timeoutCallback?.({ tempVideoPath: 'wxfile://temp/segment-1.mp4' })
    await flushPromises()
    expect(camera.startRecord).toHaveBeenCalledTimes(3)
    now = 123_000
    startOptions[2].timeoutCallback?.({ tempVideoPath: 'wxfile://temp/final.mp4' })

    expect(onMaxDuration).toHaveBeenCalledWith(123_000)

    let finishSettled = false
    const finishPromise = recorder.finish().finally(() => {
      finishSettled = true
    })
    await flushPromises()
    expect(finishSettled).toBe(false)

    now = 124_000
    releaseSegment()
    await expect(finishPromise).resolves.toEqual([
      { savedFilePath: 'wxfile://temp/segment-0.mp4', durationMs: 60_000 },
      { savedFilePath: 'wxfile://temp/segment-1.mp4', durationMs: 60_000 },
      { savedFilePath: 'wxfile://temp/final.mp4', durationMs: 2_000 }
    ])
    expect(onMaxDuration).toHaveBeenCalledTimes(1)
  })

  it('still delivers the timed-out segment when the next start fails and exposes the start error to finish', async () => {
    const { camera, startOptions } = fakeCamera()
    const delivered: string[] = []
    const unhandled: unknown[] = []
    const onUnhandled = (reason: unknown) => {
      unhandled.push(reason)
    }
    let now = 0
    camera.startRecord.mockImplementation((options: StartOptions) => {
      startOptions.push(options)
      if (startOptions.length === 1) options.success?.()
      else options.fail?.()
    })
    const recorder = new MotionTrainingRecorder({
      camera,
      now: () => now,
      onSegment: async (path) => {
        delivered.push(path)
      }
    })

    process.on('unhandledRejection', onUnhandled)
    try {
      await recorder.start()
      now = 30000
      startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://store/segment-0.mp4' })
      await flushPromises()

      expect(delivered).toEqual(['wxfile://store/segment-0.mp4'])
      await expect(recorder.finish()).rejects.toThrow('摄像头录像启动失败，请检查权限后重试')
      expect(unhandled).toEqual([])
    } finally {
      process.off('unhandledRejection', onUnhandled)
    }
  })

  it('keeps timeout onSegment rejection controlled and observable from finish', async () => {
    const { camera, startOptions } = fakeCamera()
    const unhandled: unknown[] = []
    const onUnhandled = (reason: unknown) => {
      unhandled.push(reason)
    }
    let now = 0
    const recorder = new MotionTrainingRecorder({
      camera,
      now: () => now,
      onSegment: async (path) => {
        if (path.includes('segment-0')) throw new Error('保存失败')
      }
    })

    process.on('unhandledRejection', onUnhandled)
    try {
      await recorder.start()
      now = 30000
      startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://store/segment-0.mp4' })
      await flushPromises()

      now = 42000
      const finishPromise = recorder.finish()
      expect(camera.startRecord).toHaveBeenCalledTimes(1)

      await expect(finishPromise).rejects.toThrow('保存失败')
      expect(unhandled).toEqual([])
    } finally {
      process.off('unhandledRejection', onUnhandled)
    }
  })

  it('ignores stale start callbacks from older generations when finishing the active segment', async () => {
    const { camera, startOptions, stopOptions } = fakeCamera()
    let now = 0
    const recorder = new MotionTrainingRecorder({
      camera,
      now: () => now,
      onSegment: vi.fn(async () => undefined)
    })

    await recorder.start()
    now = 30000
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://store/segment-0.mp4' })
    await flushPromises()
    startOptions[0].fail?.()

    now = 42000
    const finishPromise = recorder.finish()
    expect(camera.stopRecord).toHaveBeenCalledTimes(1)
    stopOptions[0].success?.({ tempVideoPath: 'wxfile://store/segment-1.mp4' })

    await expect(finishPromise).resolves.toEqual([
      { savedFilePath: 'wxfile://store/segment-0.mp4', durationMs: 30000 },
      { savedFilePath: 'wxfile://store/segment-1.mp4', durationMs: 12000 }
    ])
  })

  it('lets finish wait for an in-flight pause stop and returns the delivered segment', async () => {
    const { camera, stopOptions } = fakeCamera()
    let now = 1000
    const recorder = new MotionTrainingRecorder({
      camera,
      now: () => now,
      onSegment: vi.fn(async () => undefined)
    })

    await recorder.start()
    now = 4500
    const pausePromise = recorder.pause()
    const finishPromise = recorder.finish()
    stopOptions[0].success?.({ tempVideoPath: 'wxfile://store/segment-0.mp4' })

    await expect(pausePromise).resolves.toEqual({
      savedFilePath: 'wxfile://store/segment-0.mp4',
      durationMs: 3500
    })
    await expect(finishPromise).resolves.toEqual([
      { savedFilePath: 'wxfile://store/segment-0.mp4', durationMs: 3500 }
    ])
  })

  it('ignores late start failure after pause already stopped a starting generation', async () => {
    const { camera, startOptions, stopOptions } = fakeCamera()
    camera.startRecord.mockImplementation((options: StartOptions) => {
      startOptions.push(options)
    })
    let now = 1000
    const recorder = new MotionTrainingRecorder({
      camera,
      now: () => now,
      onSegment: vi.fn(async () => undefined)
    })

    const startPromise = recorder.start()
    await flushPromises()
    now = 4000
    const pausePromise = recorder.pause()
    expect(camera.stopRecord).not.toHaveBeenCalled()
    startOptions[0].success?.()
    stopOptions[0].success?.({ tempVideoPath: 'wxfile://store/segment-0.mp4' })
    startOptions[0].fail?.()

    await expect(startPromise).resolves.toBeUndefined()
    await expect(pausePromise).resolves.toEqual({
      savedFilePath: 'wxfile://store/segment-0.mp4',
      durationMs: 3000
    })
  })

  it('finishes a newly starting generation when timeout and finish happen back to back', async () => {
    const { camera, startOptions, stopOptions } = fakeCamera()
    let now = 0
    camera.startRecord.mockImplementation((options: StartOptions) => {
      startOptions.push(options)
      if (startOptions.length === 1) options.success?.()
    })
    const recorder = new MotionTrainingRecorder({
      camera,
      now: () => now,
      onSegment: vi.fn(async () => undefined)
    })

    await recorder.start()
    now = 30000
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://store/segment-0.mp4' })
    await flushPromises()
    now = 31000
    const finishPromise = recorder.finish()
    expect(camera.stopRecord).not.toHaveBeenCalled()
    startOptions[1].success?.()
    stopOptions[0].success?.({ tempVideoPath: 'wxfile://store/segment-1.mp4' })

    await expect(finishPromise).resolves.toEqual([
      { savedFilePath: 'wxfile://store/segment-0.mp4', durationMs: 30000 },
      { savedFilePath: 'wxfile://store/segment-1.mp4', durationMs: 1000 }
    ])
    expect(camera.startRecord).toHaveBeenCalledTimes(2)
  })

  it('keeps a failed final path retryable and only delivers it after retry succeeds', async () => {
    const { camera, startOptions } = fakeCamera()
    let now = 0
    let finalSegmentSaveAttempt = 0
    const onMaxDuration = vi.fn()
    const onSegment = vi.fn(async (path: string) => {
      if (path !== 'wxfile://temp/final.mp4') return
      finalSegmentSaveAttempt += 1
      if (finalSegmentSaveAttempt === 1) throw new Error('尾段保存失败')
    })
    const recorder = new MotionTrainingRecorder({
      camera,
      now: () => now,
      maxDurationMs: 122_000,
      onMaxDuration,
      onSegment
    })

    await recorder.start()
    now = 60_000
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://temp/segment-0.mp4' })
    await flushPromises()
    expect(camera.startRecord).toHaveBeenCalledTimes(2)
    now = 120_000
    startOptions[1].timeoutCallback?.({ tempVideoPath: 'wxfile://temp/segment-1.mp4' })
    await flushPromises()
    expect(camera.startRecord).toHaveBeenCalledTimes(3)
    now = 122_000
    startOptions[2].timeoutCallback?.({ tempVideoPath: 'wxfile://temp/final.mp4' })
    await flushPromises()

    expect(onMaxDuration).toHaveBeenCalledWith(122_000)
    await expect(recorder.finish()).rejects.toThrow('尾段保存失败')
    expect(recorder.hasFailedSegment()).toBe(true)

    await expect(recorder.retryFailedSegment()).resolves.toEqual({
      savedFilePath: 'wxfile://temp/final.mp4',
      durationMs: 2_000
    })
    expect(recorder.hasFailedSegment()).toBe(false)
    await expect(recorder.finish()).resolves.toEqual([
      { savedFilePath: 'wxfile://temp/segment-0.mp4', durationMs: 60_000 },
      { savedFilePath: 'wxfile://temp/segment-1.mp4', durationMs: 60_000 },
      { savedFilePath: 'wxfile://temp/final.mp4', durationMs: 2_000 }
    ])
    expect(onSegment).toHaveBeenCalledTimes(4)
  })
})


describe('recording native diagnostics', () => {
  it('preserves native start and stop errors at the recorder boundary', async () => {
    vi.useFakeTimers()
    const onNativeError = vi.fn()
    const startError = { errMsg: 'startRecord:fail permission denied', errCode: 1001 }
    const stopError = { errMsg: 'stopRecord:fail timeout' }
    const camera = {
      startRecord: vi.fn((options: any) => options.fail(startError)),
      stopRecord: vi.fn((options: any) => options.fail(stopError))
    }
    const recorder = new MotionTrainingRecorder({ camera, now: () => 1000, onSegment: vi.fn(), onNativeError })
    await expect(recorder.start()).rejects.toThrow('启动失败')
    expect(onNativeError).toHaveBeenCalledWith(startError)
    camera.startRecord.mockImplementation(options => options.success())
    const next = new MotionTrainingRecorder({ camera, now: () => 1000, onSegment: vi.fn(), onNativeError })
    await next.start()
    const stopped = next.pause().catch(error => error)
    await vi.advanceTimersByTimeAsync(10000)
    expect(await stopped).toEqual(expect.objectContaining({ message: '录像停止失败，请稍后重试' }))
    expect(onNativeError).toHaveBeenCalledWith(stopError)
  })
})

it('停止录像没有回调时保留等待，主动取消后迟到回调不保存或重启录像', async () => {
  vi.useFakeTimers()
  try {
    const { camera, stopOptions, startOptions } = fakeCamera()
    const onSegment = vi.fn()
    const recorder = new MotionTrainingRecorder({ camera, now: Date.now, onSegment })
    await recorder.start()
    const result = recorder.finish().catch(error => error)
    await vi.advanceTimersByTimeAsync(10000)
    expect(await Promise.race([result, Promise.resolve('still-pending')])).toBe('still-pending')
    recorder.discard()
    stopOptions[0].success?.({ tempVideoPath: 'late.mp4' })
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'late-timeout.mp4' })
    await flushPromises()
    expect(onSegment).not.toHaveBeenCalled()
    expect(camera.startRecord).toHaveBeenCalledTimes(1)
  } finally { vi.useRealTimers() }
})


it('主动取消正在停止的录像立即结束等待，迟到结果不再交付', async () => {
  const { camera, stopOptions } = fakeCamera()
  const onSegment = vi.fn()
  const recorder = new MotionTrainingRecorder({ camera, now: Date.now, onSegment })
  await recorder.start()
  const result = recorder.finish().catch(error => error)
  recorder.discard()
  expect(await result).toBeInstanceOf(Error)
  stopOptions[0].success?.({ tempVideoPath: 'discarded.mp4' })
  await flushPromises()
  expect(onSegment).not.toHaveBeenCalled()
})

it('完成本组遇到五秒切段启动中，应等启动确认再停止而不报停止失败', async () => {
  const { camera, startOptions } = fakeCamera()
  let nativeReady = true
  camera.startRecord.mockImplementation(options => {
    startOptions.push(options)
    if (startOptions.length === 1) options.success?.()
    else nativeReady = false
  })
  camera.stopRecord.mockImplementation(options => {
    if (!nativeReady) options.fail?.()
    else options.success?.({ tempVideoPath: 'tail.mp4' })
  })
  let now = 0
  const recorder = new MotionTrainingRecorder({ camera, now: () => now, onSegment: vi.fn() })
  await recorder.start()
  now = 5000
  startOptions[0].timeoutCallback?.({ tempVideoPath: 'first.mp4' })
  await flushPromises()
  const result = recorder.finish().catch(error => error)
  await flushPromises()
  nativeReady = true
  startOptions[1].success?.()
  expect(await result).toEqual([
    { savedFilePath: 'first.mp4', durationMs: 5000 },
    { savedFilePath: 'tail.mp4', durationMs: 0 }
  ])
})

it.each(['timeout-first', 'fail-first'])('完成本组与自动结束相撞（%s），使用自动结束的视频而不是报停止失败', async order => {
  const { camera, startOptions, stopOptions } = fakeCamera()
  let now = 0
  const onSegment = vi.fn()
  const recorder = new MotionTrainingRecorder({ camera, now: () => now, onSegment })
  await recorder.start()
  now = 4900
  const result = recorder.finish().catch(error => error)
  if (order === 'fail-first') stopOptions[0].fail?.()
  now = 5000
  startOptions[0].timeoutCallback?.({ tempVideoPath: 'complete.mp4' })
  if (order === 'timeout-first') stopOptions[0].fail?.()
  expect(await result).toEqual([{ savedFilePath: 'complete.mp4', durationMs: 5000 }])
  expect(onSegment).toHaveBeenCalledTimes(1)
  expect(camera.startRecord).toHaveBeenCalledTimes(1)
})

it('启动回调不返回时保留等待，主动取消后迟到启动不再停止或保存', async () => {
  vi.useFakeTimers()
  const { camera, startOptions } = fakeCamera()
  camera.startRecord.mockImplementation(options => { startOptions.push(options) })
  const onSegment = vi.fn()
  const recorder = new MotionTrainingRecorder({ camera, now: Date.now, onSegment })
  const started = recorder.start()
  await flushPromises()
  const finished = recorder.finish().catch(error => error)
  await vi.advanceTimersByTimeAsync(10000)
  expect(await Promise.race([finished, Promise.resolve('still-pending')])).toBe('still-pending')
  expect(camera.stopRecord).not.toHaveBeenCalled()
  recorder.discard()
  const stopsAfterDiscard = camera.stopRecord.mock.calls.length
  startOptions[0].success?.()
  await started
  expect(camera.stopRecord).toHaveBeenCalledTimes(stopsAfterDiscard)
  expect(onSegment).not.toHaveBeenCalled()
})

it('切段启动失败时完成也失败，不用已有片段冒充整组录像', async () => {
  const { camera, startOptions } = fakeCamera()
  camera.startRecord.mockImplementation(options => {
    startOptions.push(options)
    if (startOptions.length === 1) options.success?.()
  })
  const recorder = new MotionTrainingRecorder({ camera, now: Date.now, onSegment: vi.fn() })
  await recorder.start()
  startOptions[0].timeoutCallback?.({ tempVideoPath: 'first.mp4' })
  await flushPromises()
  const result = recorder.finish().catch(error => error)
  startOptions[1].fail?.()
  expect(await result).toEqual(expect.objectContaining({ message: '摄像头录像启动失败，请检查权限后重试' }))
  expect(camera.stopRecord).not.toHaveBeenCalled()
})

it('自动结束救回视频后仍等待文件保存，保存失败不假报完成且能原片重试', async () => {
  const { camera, startOptions, stopOptions } = fakeCamera()
  let rejectSave!: (error: Error) => void
  const onSegment = vi.fn().mockImplementationOnce(() => new Promise((_, reject) => { rejectSave = reject }))
  const recorder = new MotionTrainingRecorder({ camera, now: Date.now, onSegment })
  await recorder.start()
  let settled = false
  const result = recorder.finish().catch(error => error).finally(() => { settled = true })
  stopOptions[0].fail?.()
  startOptions[0].timeoutCallback?.({ tempVideoPath: 'final.mp4' })
  await flushPromises()
  expect(settled).toBe(false)
  rejectSave(new Error('保存失败'))
  expect(await result).toEqual(expect.objectContaining({ message: '保存失败' }))
  await recorder.retryFailedSegment()
  expect(await recorder.finish()).toHaveLength(1)
  expect(camera.stopRecord).toHaveBeenCalledTimes(1)
})

it('停止回调超过十秒仍接收原录像，重试完成不重复向微信发送停止请求', async () => {
  vi.useFakeTimers()
  const { camera, stopOptions } = fakeCamera()
  const onSegment = vi.fn()
  const recorder = new MotionTrainingRecorder({ camera, now: Date.now, onSegment })
  await recorder.start()
  const first = recorder.finish().catch(error => error)
  await vi.advanceTimersByTimeAsync(12000)
  const retry = recorder.finish().catch(error => error)
  stopOptions[0].success?.({ tempVideoPath: 'wxfile://late-complete.mp4' })
  const expected = [{ savedFilePath: 'wxfile://late-complete.mp4', durationMs: 12000 }]
  expect(await first).toEqual(expected)
  expect(await retry).toEqual(expected)
  expect(camera.stopRecord).toHaveBeenCalledTimes(1)
  expect(onSegment).toHaveBeenCalledTimes(1)
})

it('微信在自动结束回调返回后清理状态，续录不能在同一回调栈内启动', async () => {
  let nativeRecording = false
  let options: StartOptions | undefined
  const paths: string[] = []
  let now = 0
  // WeChat 3.16.0 _videoTaken invokes timeoutCallback BEFORE resetting
  // _isRecording. Model that boundary, including its asynchronous start ack.
  const camera = {
    startRecord: (next: StartOptions) => {
      options = next
      if (!nativeRecording) nativeRecording = true
      queueMicrotask(() => next.success?.())
    },
    stopRecord: (_options: StopOptions) => undefined
  }
  const nativeTimeout = (path: string) => {
    if (!nativeRecording) return
    options!.timeoutCallback?.({ tempVideoPath: path })
    nativeRecording = false
  }
  const recorder = new MotionTrainingRecorder({ camera, now: () => now, onSegment: path => { paths.push(path) } })
  await recorder.start()
  now = 5000; nativeTimeout('first.mp4'); await flushPromises(15)
  now = 10000; nativeTimeout('second.mp4'); await flushPromises(15)
  expect(paths).toEqual(['first.mp4', 'second.mp4'])
  recorder.discard()
})

it('自动结束回调后尚未续录就完成本组，不再启动或停止额外一段', async () => {
  const { camera, startOptions } = fakeCamera()
  let now = 0
  const recorder = new MotionTrainingRecorder({ camera, now: () => now, onSegment: vi.fn() })
  await recorder.start()
  now = 5000
  startOptions[0].timeoutCallback?.({ tempVideoPath: 'final.mp4' })
  expect(await recorder.finish()).toEqual([{ savedFilePath: 'final.mp4', durationMs: 5000 }])
  expect(camera.startRecord).toHaveBeenCalledTimes(1)
  expect(camera.stopRecord).not.toHaveBeenCalled()
})

it('慢停止提示后收到明确失败回调，仍结束等待并允许重试', async () => {
  vi.useFakeTimers()
  const { camera, stopOptions } = fakeCamera()
  const onStopSlow = vi.fn()
  const recorder = new MotionTrainingRecorder({ camera, now: Date.now, onSegment: vi.fn(), onStopSlow })
  await recorder.start()
  const result = recorder.finish().catch(error => error)
  await vi.advanceTimersByTimeAsync(10000)
  expect(onStopSlow).toHaveBeenCalledWith('stopping')
  stopOptions[0].fail?.()
  expect(await result).toEqual(expect.objectContaining({ message: '录像停止失败，请稍后重试' }))
})

it('回放真机第18段启动974毫秒后完成：保留自动结束回调，保存后不续录', async () => {
  vi.useFakeTimers()
  const paths: string[] = []
  let nativeTimer: ReturnType<typeof setTimeout>
  const camera = {
    startRecord: vi.fn((options: StartOptions) => {
      options.success?.()
      nativeTimer = setTimeout(() => options.timeoutCallback?.({ tempVideoPath: 'native-tail.mp4' }), 5229)
    }),
    stopRecord: vi.fn((options: StopOptions) => {
      // Actual WeChat stopRecord removes the timeout delivery even on failure.
      clearTimeout(nativeTimer)
      options.fail?.()
    })
  }
  const recorder = new MotionTrainingRecorder({ camera, now: Date.now, finishAtSegmentBoundary: true,
    onSegment: path => { paths.push(path) } })
  await recorder.start()
  await vi.advanceTimersByTimeAsync(974)
  let finished = false
  const finishing = recorder.finish().then(() => { finished = true })
  await vi.advanceTimersByTimeAsync(4255)
  expect(finished).toBe(true)
  await finishing
  expect(paths).toEqual(['native-tail.mp4'])
  expect(camera.stopRecord).not.toHaveBeenCalled()
  expect(camera.startRecord).toHaveBeenCalledTimes(1)
})
