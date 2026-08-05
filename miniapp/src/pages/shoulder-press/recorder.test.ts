import { describe, expect, it, vi } from 'vitest'

import { ShoulderPressRecorder } from './recorder'

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

async function flushPromises(times = 6) {
  for (let index = 0; index < times; index += 1) {
    await Promise.resolve()
  }
}

describe('ShoulderPressRecorder', () => {
  it('starts the next recording before asynchronously delivering a timeout segment', async () => {
    const { camera, startOptions } = fakeCamera()
    const order: string[] = []
    let now = 0
    const recorder = new ShoulderPressRecorder({
      camera,
      now: () => now,
      onSegment: async (path, durationMs) => {
        order.push(`segment:${path}:${durationMs}`)
      }
    })
    camera.startRecord.mockImplementation((options: StartOptions) => {
      startOptions.push(options)
      order.push('start')
      options.success?.()
    })

    await recorder.start()
    expect(startOptions[0].timeout).toBe(15)
    now = 30000
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://store/segment-0.mp4' })
    await Promise.resolve()

    expect(startOptions[1].timeout).toBe(15)
    expect(order).toEqual([
      'start',
      'start',
      'segment:wxfile://store/segment-0.mp4:30000'
    ])
  })

  it('pause saves segments at least two seconds long and discards shorter files', async () => {
    const { camera, stopOptions } = fakeCamera()
    let now = 1000
    const delivered: Array<{ path: string; durationMs: number }> = []
    const onPause = vi.fn()
    const recorder = new ShoulderPressRecorder({
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

  it('delivers the same path only once when timeout and stop success race', async () => {
    const { camera, startOptions, stopOptions } = fakeCamera()
    let now = 0
    const delivered: string[] = []
    const recorder = new ShoulderPressRecorder({
      camera,
      now: () => now,
      onSegment: async (path) => {
        delivered.push(path)
      }
    })

    await recorder.start()
    now = 30000
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://store/segment-0.mp4' })
    const finishPromise = recorder.finish()
    stopOptions[0].success?.({ tempVideoPath: 'wxfile://store/segment-0.mp4' })
    await finishPromise
    await Promise.resolve()

    expect(delivered).toEqual(['wxfile://store/segment-0.mp4'])
  })

  it('finish stops automatic continuation and returns all delivered segments', async () => {
    const { camera, startOptions, stopOptions } = fakeCamera()
    let now = 0
    const recorder = new ShoulderPressRecorder({
      camera,
      now: () => now,
      onSegment: vi.fn(async () => undefined)
    })

    await recorder.start()
    now = 30000
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://store/segment-0.mp4' })
    await Promise.resolve()

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

  it('uses the remaining duration for generation 160 and never records past the upload contract', async () => {
    const { camera, startOptions } = fakeCamera()
    let now = 0
    const onMaxDuration = vi.fn()
    const recorder = new ShoulderPressRecorder({
      camera,
      now: () => now,
      maxDurationMs: 2_397_000,
      onMaxDuration,
      onSegment: vi.fn(async () => undefined)
    })

    await recorder.start()
    for (let index = 0; index < 159; index += 1) {
      now = (index + 1) * 15_000
      startOptions[index].timeoutCallback?.({ tempVideoPath: `wxfile://store/segment-${index}.mp4` })
      await flushPromises()
    }

    expect(camera.startRecord).toHaveBeenCalledTimes(160)
    expect(startOptions.slice(0, 159).every((options) => options.timeout === 15)).toBe(true)
    expect(startOptions[159].timeout).toBe(12)

    now = 2_397_000
    startOptions[159].timeoutCallback?.({ tempVideoPath: 'wxfile://store/segment-159.mp4' })
    const finishPromise = recorder.finish()
    await flushPromises()

    expect(camera.startRecord).toHaveBeenCalledTimes(160)
    const segments = await finishPromise
    expect(segments).toHaveLength(160)
    expect(segments.reduce((total, segment) => total + segment.durationMs, 0)).toBe(2_397_000)
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
    const recorder = new ShoulderPressRecorder({
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
    const { camera, startOptions, stopOptions } = fakeCamera()
    const unhandled: unknown[] = []
    const onUnhandled = (reason: unknown) => {
      unhandled.push(reason)
    }
    let now = 0
    const recorder = new ShoulderPressRecorder({
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
      stopOptions[0].success?.({ tempVideoPath: 'wxfile://store/segment-1.mp4' })

      await expect(finishPromise).rejects.toThrow('保存失败')
      expect(unhandled).toEqual([])
    } finally {
      process.off('unhandledRejection', onUnhandled)
    }
  })

  it('ignores stale start callbacks from older generations when finishing the active segment', async () => {
    const { camera, startOptions, stopOptions } = fakeCamera()
    let now = 0
    const recorder = new ShoulderPressRecorder({
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
    const recorder = new ShoulderPressRecorder({
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
    const recorder = new ShoulderPressRecorder({
      camera,
      now: () => now,
      onSegment: vi.fn(async () => undefined)
    })

    const startPromise = recorder.start()
    await Promise.resolve()
    now = 4000
    const pausePromise = recorder.pause()
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
    const recorder = new ShoulderPressRecorder({
      camera,
      now: () => now,
      onSegment: vi.fn(async () => undefined)
    })

    await recorder.start()
    now = 30000
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://store/segment-0.mp4' })
    now = 31000
    const finishPromise = recorder.finish()
    stopOptions[0].success?.({ tempVideoPath: 'wxfile://store/segment-1.mp4' })
    startOptions[1].success?.()

    await expect(finishPromise).resolves.toEqual([
      { savedFilePath: 'wxfile://store/segment-0.mp4', durationMs: 30000 },
      { savedFilePath: 'wxfile://store/segment-1.mp4', durationMs: 1000 }
    ])
    expect(camera.startRecord).toHaveBeenCalledTimes(2)
  })

  it('keeps a failed final path retryable and only delivers it after retry succeeds', async () => {
    const { camera, startOptions } = fakeCamera()
    let now = 0
    let saveAttempt = 0
    const onMaxDuration = vi.fn()
    const onSegment = vi.fn(async () => {
      saveAttempt += 1
      if (saveAttempt === 1) throw new Error('尾段保存失败')
    })
    const recorder = new ShoulderPressRecorder({
      camera,
      now: () => now,
      maxDurationMs: 30_000,
      onMaxDuration,
      onSegment
    })

    await recorder.start()
    now = 30_000
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://temp/final.mp4' })
    await flushPromises()

    expect(onMaxDuration).not.toHaveBeenCalled()
    await expect(recorder.finish()).rejects.toThrow('尾段保存失败')
    expect(recorder.hasFailedSegment()).toBe(true)

    await expect(recorder.retryFailedSegment()).resolves.toEqual({
      savedFilePath: 'wxfile://temp/final.mp4',
      durationMs: 30_000
    })
    expect(recorder.hasFailedSegment()).toBe(false)
    await expect(recorder.finish()).resolves.toEqual([
      { savedFilePath: 'wxfile://temp/final.mp4', durationMs: 30_000 }
    ])
    expect(onSegment).toHaveBeenCalledTimes(2)
  })
})
