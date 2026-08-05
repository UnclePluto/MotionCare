type RecordStartOptions = {
  success?: () => void
  fail?: () => void
  timeout?: number
  timeoutCallback?: (result: { tempVideoPath: string }) => void
}

type RecordStopOptions = {
  success?: (result: { tempVideoPath: string }) => void
  fail?: () => void
}

type CameraContext = {
  startRecord: (options: RecordStartOptions) => void
  stopRecord: (options: RecordStopOptions) => void
}

export type ShoulderPressRecordedSegment = {
  savedFilePath: string
  durationMs: number
}

type RecorderMode = 'idle' | 'recording' | 'pausing' | 'finishing'
type GenerationState = 'starting' | 'recording' | 'stopping' | 'stopped' | 'failed'

type RecordingGeneration = {
  id: number
  startedAt: number
  requestedDurationMs: number
  state: GenerationState
}

const MIN_PAUSE_SEGMENT_MS = 2000
const TIMEOUT_SEGMENT_MS = 15000

export class ShoulderPressRecorder {
  private readonly camera: CameraContext
  private readonly now: () => number
  private readonly onSegment: (path: string, durationMs: number) => Promise<void> | void
  private readonly onPause?: () => void
  private readonly onMaxDuration?: () => void
  private readonly maxDurationMs: number
  private generation = 0
  private mode: RecorderMode = 'idle'
  private currentGeneration: RecordingGeneration | null = null
  private stoppingPromise: Promise<ShoulderPressRecordedSegment | null> | null = null
  private readonly pendingDeliveries = new Set<Promise<unknown>>()
  private pendingError: Error | null = null
  private readonly deliveredPaths = new Set<string>()
  private readonly deliveriesByPath = new Map<string, Promise<ShoulderPressRecordedSegment | null>>()
  private readonly deliveredSegments: ShoulderPressRecordedSegment[] = []
  private failedSegment: ShoulderPressRecordedSegment | null = null
  private recordedDurationMs = 0

  constructor(input: {
    camera: CameraContext
    now: () => number
    onSegment: (path: string, durationMs: number) => Promise<void> | void
    onPause?: () => void
    onMaxDuration?: () => void
    maxDurationMs?: number
  }) {
    this.camera = input.camera
    this.now = input.now
    this.onSegment = input.onSegment
    this.onPause = input.onPause
    this.onMaxDuration = input.onMaxDuration
    this.maxDurationMs = input.maxDurationMs ?? Number.POSITIVE_INFINITY
  }

  async start(): Promise<void> {
    await this.waitForPendingDeliveries()
    if (this.mode === 'recording') return Promise.resolve()
    this.mode = 'recording'
    return this.startGeneration()
  }

  pause(): Promise<ShoulderPressRecordedSegment | null> {
    if (this.mode !== 'recording') return Promise.resolve(null)
    this.mode = 'pausing'
    const generation = this.generation
    const stopping = this.stopCurrent(generation, true)
    this.stoppingPromise = stopping
    return stopping.finally(() => {
      this.onPause?.()
      if (this.mode === 'pausing') this.mode = 'idle'
      if (this.stoppingPromise === stopping) this.stoppingPromise = null
    })
  }

  async finish(): Promise<ShoulderPressRecordedSegment[]> {
    if (this.mode === 'pausing' || this.mode === 'finishing') {
      await this.stoppingPromise
      await this.waitForPendingDeliveries()
      return this.deliveredSegments.slice()
    }
    if (this.mode !== 'recording') {
      await this.waitForPendingDeliveries()
      return this.deliveredSegments.slice()
    }

    this.mode = 'finishing'
    const generation = this.generation
    const stopping = this.stopCurrent(generation, false)
    this.stoppingPromise = stopping
    try {
      await stopping
      await this.waitForPendingDeliveries()
      return this.deliveredSegments.slice()
    } finally {
      if (this.mode === 'finishing') this.mode = 'idle'
      if (this.stoppingPromise === stopping) this.stoppingPromise = null
    }
  }

  hasFailedSegment(): boolean {
    return this.failedSegment !== null
  }

  async retryFailedSegment(): Promise<ShoulderPressRecordedSegment | null> {
    const failedSegment = this.failedSegment
    if (!failedSegment) return null
    this.pendingError = null
    return this.trackDelivery(
      this.deliver(failedSegment.savedFilePath, failedSegment.durationMs),
      true
    )
  }

  abandonFailedSegment(): ShoulderPressRecordedSegment | null {
    const failedSegment = this.failedSegment
    this.failedSegment = null
    this.pendingError = null
    return failedSegment
  }

  private startGeneration(): Promise<void> {
    const remainingMs = this.maxDurationMs - this.recordedDurationMs
    if (remainingMs < 1000) {
      this.mode = 'finishing'
      this.currentGeneration = null
      this.onMaxDuration?.()
      return Promise.resolve()
    }
    const timeoutSeconds = Math.min(
      TIMEOUT_SEGMENT_MS / 1000,
      Math.floor(remainingMs / 1000)
    )
    const generation: RecordingGeneration = {
      id: this.generation + 1,
      startedAt: this.now(),
      requestedDurationMs: timeoutSeconds * 1000,
      state: 'starting'
    }
    this.generation = generation.id
    this.currentGeneration = generation

    return new Promise((resolve, reject) => {
      this.camera.startRecord({
        timeout: timeoutSeconds,
        success: () => {
          if (!this.isStartingGeneration(generation)) {
            resolve()
            return
          }
          generation.state = 'recording'
          resolve()
        },
        fail: () => {
          if (!this.isStartingGeneration(generation)) {
            resolve()
            return
          }
          generation.state = 'failed'
          this.mode = 'idle'
          this.currentGeneration = null
          const error = new Error('摄像头录像启动失败，请检查权限后重试')
          this.recordError(error)
          reject(error)
        },
        timeoutCallback: (result) => {
          this.handleTimeout(generation.id, result.tempVideoPath)
        }
      })
    })
  }

  private handleTimeout(generationId: number, path: string): void {
    const generation = this.currentGeneration
    if (!generation || generation.id !== generationId || this.mode !== 'recording') return
    generation.state = 'stopped'
    const durationMs = this.durationSinceStart(generation, generation.requestedDurationMs)
    this.recordedDurationMs += durationMs
    const reachedLimit = generation.requestedDurationMs < TIMEOUT_SEGMENT_MS ||
      this.recordedDurationMs >= this.maxDurationMs

    if (reachedLimit) {
      this.mode = 'finishing'
      this.currentGeneration = null
    } else {
      const startPromise = this.startGeneration().catch((error: unknown) => {
        this.recordError(error)
      })
      void startPromise
    }

    const delivery = this.trackDelivery(this.deliver(path, durationMs), false)
    if (reachedLimit) {
      void delivery.then((segment) => {
        if (segment) this.onMaxDuration?.()
      })
    }
    void delivery
  }

  private stopCurrent(generation: number, discardShortPause: boolean): Promise<ShoulderPressRecordedSegment | null> {
    const targetGeneration = this.currentGeneration
    if (!targetGeneration || targetGeneration.id !== generation) return Promise.resolve(null)
    targetGeneration.state = 'stopping'

    return new Promise((resolve, reject) => {
      this.camera.stopRecord({
        success: (result) => {
          if (!this.isCurrentGeneration(generation)) {
            resolve(null)
            return
          }
          targetGeneration.state = 'stopped'
          const durationMs = this.durationSinceStart(targetGeneration, 0)
          if (discardShortPause && durationMs < MIN_PAUSE_SEGMENT_MS) {
            resolve(null)
            return
          }
          this.recordedDurationMs += durationMs
          this.trackDelivery(this.deliver(result.tempVideoPath, durationMs), true)
            .then((segment) => resolve(segment))
            .catch((error: unknown) => reject(error instanceof Error ? error : new Error('录像分段保存失败')))
        },
        fail: () => {
          if (!this.isCurrentGeneration(generation)) {
            resolve(null)
            return
          }
          targetGeneration.state = 'failed'
          const error = new Error('录像停止失败，请稍后重试')
          this.recordError(error)
          reject(error)
        }
      })
    })
  }

  private durationSinceStart(generation: RecordingGeneration, fallbackMs: number): number {
    const durationMs = Math.max(0, Math.round(this.now() - generation.startedAt))
    return durationMs > 0 ? durationMs : fallbackMs
  }

  private deliver(path: string, durationMs: number): Promise<ShoulderPressRecordedSegment | null> {
    if (!path || this.deliveredPaths.has(path)) return Promise.resolve(null)
    const existing = this.deliveriesByPath.get(path)
    if (existing) return existing
    const segment = { savedFilePath: path, durationMs }
    let delivery: Promise<ShoulderPressRecordedSegment | null>
    delivery = Promise.resolve()
      .then(() => this.onSegment(path, durationMs))
      .then(() => {
        this.deliveredPaths.add(path)
        if (this.failedSegment?.savedFilePath === path) this.failedSegment = null
        this.deliveredSegments.push(segment)
        return segment
      })
      .catch((error: unknown) => {
        this.failedSegment = segment
        throw error
      })
      .finally(() => {
        if (this.deliveriesByPath.get(path) === delivery) {
          this.deliveriesByPath.delete(path)
        }
      })
    this.deliveriesByPath.set(path, delivery)
    return delivery
  }

  private isCurrentGeneration(generation: number): boolean {
    return this.currentGeneration?.id === generation
  }

  private isStartingGeneration(generation: RecordingGeneration): boolean {
    return this.currentGeneration?.id === generation.id &&
      this.mode === 'recording' &&
      generation.state === 'starting'
  }

  private trackDelivery<T>(promise: Promise<T>, surfaceError: boolean): Promise<T | null> {
    let tracked: Promise<T | null>
    tracked = promise
      .catch((error: unknown) => {
        this.recordError(error)
        if (surfaceError) throw this.toError(error)
        return null
      })
      .finally(() => {
        this.pendingDeliveries.delete(tracked)
      })
    this.pendingDeliveries.add(tracked)
    return tracked
  }

  private async waitForPendingDeliveries(): Promise<void> {
    if (this.pendingDeliveries.size > 0) {
      await Promise.allSettled([...this.pendingDeliveries])
    }
    const error = this.pendingError
    this.pendingError = null
    if (error) throw error
  }

  private recordError(error: unknown): void {
    if (!this.pendingError) this.pendingError = this.toError(error)
  }

  private toError(error: unknown): Error {
    return error instanceof Error ? error : new Error('录像分段保存失败')
  }
}
