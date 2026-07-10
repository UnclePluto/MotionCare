import { describe, expect, it, vi } from 'vitest'

import { ShoulderPressRecorder } from './recorder'

type StartOptions = {
  success?: () => void
  fail?: () => void
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
    now = 30000
    startOptions[0].timeoutCallback?.({ tempVideoPath: 'wxfile://store/segment-0.mp4' })
    await Promise.resolve()

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
})
