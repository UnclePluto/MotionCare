type RecordStartOptions = {
  success?: () => void
  fail?: (error?: unknown) => void
  timeout?: number
  timeoutCallback?: (result: { tempVideoPath: string }) => void
}

type RecordStopOptions = {
  success?: (result: { tempVideoPath: string }) => void
  fail?: (error?: unknown) => void
}

export type CameraContext = {
  startRecord: (options: RecordStartOptions) => void
  stopRecord: (options: RecordStopOptions) => void
}

export type MotionTrainingRecordedSegment = {
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
  timeoutHandled: boolean
  stopWhenReady?: () => void
  stopOnStartFailure?: (error: Error) => void
  stopOnTimeout?: (delivery: Promise<MotionTrainingRecordedSegment | null>) => void
}

const MIN_PAUSE_SEGMENT_MS = 2000
export const MOTION_TRAINING_SEGMENT_DURATION_MS = 60_000

export class MotionTrainingRecorder {
  private readonly camera: CameraContext
  private readonly now: () => number
  private readonly onSegment: (path: string, durationMs: number) => Promise<void> | void
  private readonly onNativeError?: (error: unknown) => void
  private readonly onRecordingChange?: (active: boolean, recordedDurationMs: number) => void
  private readonly onPause?: () => void
  private readonly canContinueRecording?: () => boolean
  private readonly onMaxDuration?: (cutoffMs: number) => void
  private readonly onStopped?: (endedAtMs: number) => void
  private readonly onStopSlow?: (phase: 'starting' | 'stopping') => void
  private readonly finishAtSegmentBoundary: boolean
  private readonly segmentDurationMs: () => number
  private readonly maxDurationMs: number
  private generation = 0
  private mode: RecorderMode = 'idle'
  private currentGeneration: RecordingGeneration | null = null
  private cancelStop: (() => void) | null = null
  private stopSlowPhase: 'starting' | 'stopping' | null = null
  private stoppingPromise: Promise<MotionTrainingRecordedSegment | null> | null = null
  private readonly pendingDeliveries = new Set<Promise<unknown>>()
  private pendingError: Error | null = null
  private readonly deliveredPaths = new Set<string>()
  private readonly deliveriesByPath = new Map<string, Promise<MotionTrainingRecordedSegment | null>>()
  private readonly deliveredSegments: MotionTrainingRecordedSegment[] = []
  private failedSegment: MotionTrainingRecordedSegment | null = null
  private recordedDurationMs = 0

  constructor(input: {
    camera: CameraContext
    now: () => number
    onSegment: (path: string, durationMs: number) => Promise<void> | void
    onNativeError?: (error: unknown) => void
    onRecordingChange?: (active: boolean, recordedDurationMs: number) => void
    onPause?: () => void
    canContinueRecording?: () => boolean
    onMaxDuration?: (cutoffMs: number) => void
    onStopped?: (endedAtMs: number) => void
    onStopSlow?: (phase: 'starting' | 'stopping') => void
    finishAtSegmentBoundary?: boolean
    segmentDurationMs?: () => number
    maxDurationMs?: number
  }) {
    this.segmentDurationMs = input.segmentDurationMs ?? (() => MOTION_TRAINING_SEGMENT_DURATION_MS)
    this.finishAtSegmentBoundary = input.finishAtSegmentBoundary ?? false
    this.onNativeError = input.onNativeError
    this.camera = input.camera
    this.now = input.now
    this.onSegment = input.onSegment
    this.onRecordingChange = input.onRecordingChange
    this.onPause = input.onPause
    this.canContinueRecording = input.canContinueRecording
    this.onMaxDuration = input.onMaxDuration
    this.onStopped = input.onStopped
    this.onStopSlow = input.onStopSlow
    this.maxDurationMs = input.maxDurationMs ?? Number.POSITIVE_INFINITY
  }

  async start(): Promise<void> {
    await this.waitForPendingDeliveries()
    if (this.mode === 'recording') return Promise.resolve()
    if (this.canContinueRecording?.() === false) throw new Error('录像空间正在清理，请等待上传完成后继续')
    this.mode = 'recording'
    return this.startGeneration()
  }

  pause(options: { preserveShortTail?: boolean } = {}): Promise<MotionTrainingRecordedSegment | null> {
    if (this.mode !== 'recording') return Promise.resolve(null)
    this.mode = 'pausing'
    const generation = this.generation
    const stopping = this.stopCurrent(generation, !options.preserveShortTail).then(async segment => {
      await this.waitForPendingDeliveries()
      return segment
    })
    this.stoppingPromise = stopping
    return stopping.finally(() => {
      this.onPause?.()
      if (this.mode === 'pausing') this.mode = 'idle'
      if (this.stoppingPromise === stopping) this.stoppingPromise = null
    })
  }

  async finish(): Promise<MotionTrainingRecordedSegment[]> {
    if (this.mode === 'pausing' || this.mode === 'finishing') {
      if (this.stopSlowPhase) this.onStopSlow?.(this.stopSlowPhase)
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
      if (this.mode === 'finishing') {
        this.mode = (
          this.currentGeneration?.id === generation &&
          (this.currentGeneration.state === 'recording' || this.currentGeneration.state === 'starting')
        ) ? 'recording' : 'idle'
      }
      if (this.stoppingPromise === stopping) this.stoppingPromise = null
    }
  }

  discard(): void {
    const shouldStop = this.currentGeneration?.state === 'recording' || this.currentGeneration?.state === 'starting'
    this.mode = 'idle'
    this.currentGeneration = null
    this.cancelStop?.()
    this.cancelStop = null
    if (shouldStop) {
      try { this.camera.stopRecord({ success: () => undefined, fail: () => undefined }) } catch { /* native camera is being replaced */ }
    }
  }

  hasFailedSegment(): boolean {
    return this.failedSegment !== null
  }

  async retryFailedSegment(): Promise<MotionTrainingRecordedSegment | null> {
    const failedSegment = this.failedSegment
    if (!failedSegment) return null
    this.pendingError = null
    return this.trackDelivery(
      this.deliver(failedSegment.savedFilePath, failedSegment.durationMs),
      true
    )
  }

  abandonFailedSegment(): MotionTrainingRecordedSegment | null {
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
      this.onMaxDuration?.(this.now())
      return Promise.resolve()
    }
    const timeoutSeconds = Math.min(
      this.segmentDurationMs() === 30_000 ? 30 : 60,
      Math.floor(remainingMs / 1000)
    )
    const generation: RecordingGeneration = {
      id: this.generation + 1,
      startedAt: this.now(),
      requestedDurationMs: timeoutSeconds * 1000,
      state: 'starting',
      timeoutHandled: false
    }
    this.generation = generation.id
    this.currentGeneration = generation

    return new Promise((resolve, reject) => {
      const startOptions: RecordStartOptions = {
        timeout: timeoutSeconds,
        success: () => {
          if (!this.isStartingGeneration(generation)) {
            resolve()
            return
          }
          generation.state = 'recording'
          this.onRecordingChange?.(true, this.recordedDurationMs)
          generation.stopWhenReady?.()
          resolve()
        },
        fail: (nativeError) => {
          if (!this.isStartingGeneration(generation)) {
            resolve()
            return
          }
          this.diagnose(nativeError)
          generation.state = 'failed'
          this.mode = 'idle'
          this.currentGeneration = null
          const error = new Error('摄像头录像启动失败，请检查权限后重试')
          this.recordError(error)
          generation.stopOnStartFailure?.(error)
          reject(error)
        },
        timeoutCallback: (result) => {
          this.handleTimeout(generation.id, result.tempVideoPath)
        }
      }
      try { this.camera.startRecord(startOptions) } catch (error) { startOptions.fail?.(error) }
    })
  }

  private handleTimeout(generationId: number, path: string): void {
    const generation = this.currentGeneration
    if (!generation || generation.id !== generationId || generation.timeoutHandled) return
    const finishStopPending = (this.mode === 'finishing' || this.mode === 'pausing') && !!generation.stopOnTimeout
    if ((this.mode !== 'recording' && !finishStopPending) || !path) return

    generation.timeoutHandled = true
    const cutoffMs = this.now()
    const durationMs = this.durationSinceStart(
      generation,
      generation.requestedDurationMs,
      cutoffMs
    )
    this.recordedDurationMs += durationMs
    this.onRecordingChange?.(false, this.recordedDurationMs)
    const reachedLimit = this.maxDurationMs - this.recordedDurationMs < 1000
    const delivery = this.trackDelivery(this.deliver(path, durationMs), false)
    if (!finishStopPending && !reachedLimit) {
      // Leave the native callback first, then admit another file only after its
      // predecessor's metadata is persisted. Upload remains asynchronous.
      void delivery.then(segment => {
        if (this.mode !== 'recording' || this.currentGeneration !== generation) return
        if (!segment || this.canContinueRecording?.() === false) {
          this.mode = 'idle'
          this.onPause?.()
          return
        }
        return this.startGeneration()
      }).catch((error: unknown) => this.recordError(error))
    }

    if (finishStopPending) {
      generation.state = 'stopped'
      if (this.mode === 'finishing') this.onStopped?.(cutoffMs)
      if (reachedLimit) this.onMaxDuration?.(cutoffMs)
      generation.stopOnTimeout?.(delivery)
      void delivery
      return
    }

    generation.state = 'stopped'
    if (reachedLimit) {
      this.mode = 'finishing'
      this.currentGeneration = null
    }

    if (reachedLimit) {
      this.onMaxDuration?.(cutoffMs)
    }
    void delivery
  }

  private stopCurrent(generation: number, discardShortPause: boolean): Promise<MotionTrainingRecordedSegment | null> {
    const targetGeneration = this.currentGeneration
    if (!targetGeneration || targetGeneration.id !== generation || targetGeneration.state === 'stopped') return Promise.resolve(null)
    const starting = targetGeneration.state === 'starting'

    return new Promise((resolve, reject) => {
      let settled = false
      let nativeStopFailed = false
      let nativeStopError: unknown
      let waitExpired = false
      const settleNative = () => {
        if (settled) return false
        settled = true
        this.stopSlowPhase = null
        clearTimeout(timer)
        targetGeneration.stopWhenReady = undefined
        targetGeneration.stopOnStartFailure = undefined
        targetGeneration.stopOnTimeout = undefined
        if (this.cancelStop === cancel) this.cancelStop = null
        return true
      }
      const cancel = () => { if (settleNative()) reject(new Error('本组录像已取消')) }
      const failNative = () => {
        if (!settleNative()) return
        if (this.isCurrentGeneration(generation) && targetGeneration.state === 'stopping') targetGeneration.state = 'recording'
        this.diagnose(nativeStopError)
        reject(new Error('录像停止失败，请稍后重试'))
      }
      const timer = setTimeout(() => {
        waitExpired = true
        if (!nativeStopFailed) {
          // A slow native operation still owns the video callback. Abandoning
          // that callback loses the video and a second stop cannot recover it.
          this.diagnose({ errMsg: 'stopRecord:fail timeout' })
          this.stopSlowPhase = targetGeneration.state === 'starting' ? 'starting' : 'stopping'
          this.onStopSlow?.(this.stopSlowPhase)
          return
        }
        failNative()
      }, 10000)
      this.cancelStop = cancel
      // Timeout and explicit stop are two native results for the same recording.
      // Either valid video completes it; do not stop an already-ended segment again.
      targetGeneration.stopOnTimeout = delivery => { if (settleNative()) delivery.then(resolve, reject) }
      targetGeneration.stopOnStartFailure = error => { if (settleNative()) reject(error) }
      const stopOptions: RecordStopOptions = {
        success: (result) => {
          if (!result.tempVideoPath) {
            stopOptions.fail?.({ errMsg: 'stopRecord:fail invalid response' })
            return
          }
          if (!settleNative()) return
          if (!this.isCurrentGeneration(generation)) {
            resolve(null)
            return
          }
          targetGeneration.state = 'stopped'
          if (this.mode === 'finishing' && !targetGeneration.timeoutHandled) this.onStopped?.(this.now())
          if (targetGeneration.timeoutHandled) {
            resolve(null)
            return
          }
          const durationMs = this.durationSinceStart(targetGeneration, 0)
          if (discardShortPause && durationMs < MIN_PAUSE_SEGMENT_MS) {
            resolve(null)
            return
          }
          this.recordedDurationMs += durationMs
          this.onRecordingChange?.(false, this.recordedDurationMs)
          this.trackDelivery(this.deliver(result.tempVideoPath, durationMs), true)
            .then((segment) => resolve(segment))
            .catch((error: unknown) => reject(error instanceof Error ? error : new Error('录像分段保存失败')))
        },
        fail: (nativeError) => {
          if (settled) return
          // Native timeout may have stopped recording while its video is still
          // queued. Keep waiting for that result within the existing deadline.
          nativeStopFailed = true
          nativeStopError = nativeError
          if (waitExpired) failNative()
        }
      }
      const stop = () => {
        if (settled || !this.isCurrentGeneration(generation)) return
        targetGeneration.state = 'stopping'
        try { this.camera.stopRecord(stopOptions) } catch (error) { stopOptions.fail?.(error) }
      }
      // Counted sets finish through the existing native timeout callback. An
      // explicit stop removes that callback in WeChat even when stop fails.
      if (this.finishAtSegmentBoundary && !discardShortPause) return
      if (starting) targetGeneration.stopWhenReady = stop
      else stop()
    })
  }

  private diagnose(error: unknown): void {
    try { this.onNativeError?.(error) } catch { /* isolated from recording */ }
  }

  private durationSinceStart(
    generation: RecordingGeneration,
    fallbackMs: number,
    endedAtMs = this.now()
  ): number {
    const durationMs = Math.max(0, Math.round(endedAtMs - generation.startedAt))
    return durationMs > 0 ? durationMs : fallbackMs
  }

  private deliver(path: string, durationMs: number): Promise<MotionTrainingRecordedSegment | null> {
    if (!path || this.deliveredPaths.has(path)) return Promise.resolve(null)
    const existing = this.deliveriesByPath.get(path)
    if (existing) return existing
    const segment = { savedFilePath: path, durationMs }
    let delivery: Promise<MotionTrainingRecordedSegment | null>
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
    if (this.failedSegment) throw new Error('录像分段保存失败，请重试保存后再结束训练')
  }

  private recordError(error: unknown): void {
    if (!this.pendingError) this.pendingError = this.toError(error)
  }

  private toError(error: unknown): Error {
    return error instanceof Error ? error : new Error('录像分段保存失败')
  }
}
