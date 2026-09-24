import type { CameraContext, MotionTrainingRecordedSegment } from './recorder'

const SEGMENT_MS = 5000
const SLOW_MS = 10000
const DEADLINE_MS = 30000
// The app owns normal segmentation. The SDK timer must not race our stop.
const NATIVE_TIMEOUT_SECONDS = 60

export type CountedRecorderEvent = 'segment_stop' | 'finish_stop' | 'discard_stop' | 'start_timeout' | 'stop_timeout' | 'recording_failed' | 'duration_limit'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  // Automatic segments can fail before the user presses Finish.
  void promise.catch(() => undefined)
  return { promise, resolve, reject }
}

type Generation = {
  state: 'starting' | 'recording' | 'stopping' | 'stopped' | 'failed'
  startedAt: number
  stoppedAt?: number
  start: ReturnType<typeof deferred<void>>
  video: ReturnType<typeof deferred<MotionTrainingRecordedSegment>>
  timers: Set<ReturnType<typeof setTimeout>>
  segment?: MotionTrainingRecordedSegment
  delivery?: Promise<void>
}

type Options = {
  camera: CameraContext
  now: () => number
  onSegment: (path: string, durationMs: number) => Promise<void> | void
  onNativeError?: (error: unknown) => void
  onFatalError?: (error: Error) => void
  onStopSlow?: (phase: 'starting' | 'stopping') => void
  onStopped?: (endedAtMs: number) => void
  onMaxDuration?: (cutoffMs: number) => void
  onEvent?: (event: CountedRecorderEvent) => void
  maxDurationMs?: number
}

/** One instance owns one counted attempt. Failed native operations require a new camera. */
export class CountedTrainingRecorder {
  private mode: 'idle' | 'recording' | 'finishing' | 'completed' | 'failed' | 'discarded' = 'idle'
  private current: Generation | null = null
  private fatalError: Error | null = null
  private readonly interruption = deferred<never>()
  private finishing: Promise<MotionTrainingRecordedSegment[]> | null = null
  private continuation?: ReturnType<typeof setTimeout>
  private failedSave: Generation | null = null
  private readonly segments: MotionTrainingRecordedSegment[] = []
  private recordedMs = 0
  private notifiedStopped = false
  private slowPhase: 'starting' | 'stopping' | null = null

  constructor(private readonly options: Options) {}

  async start(): Promise<void> {
    this.checkActive()
    if (this.mode !== 'idle') return this.current?.start.promise
    this.mode = 'recording'
    return this.startGeneration()
  }

  finish(): Promise<MotionTrainingRecordedSegment[]> {
    if (this.fatalError) return Promise.reject(this.fatalError)
    if (this.mode === 'completed') return Promise.resolve(this.segments.slice())
    if (this.finishing) {
      if (this.slowPhase) this.options.onStopSlow?.(this.slowPhase)
      return this.finishing
    }
    this.mode = 'finishing'
    clearTimeout(this.continuation)
    const generation = this.current
    if (!generation) return Promise.resolve(this.segments.slice())
    this.stop(generation, 'finish_stop')
    if (this.slowPhase) this.options.onStopSlow?.(this.slowPhase)
    const collect = async () => {
      await generation.video.promise
      await generation.delivery
      this.checkActive()
      this.mode = 'completed'
      if (!this.notifiedStopped) {
        this.notifiedStopped = true
        this.options.onStopped?.(generation.stoppedAt!)
      }
      return this.segments.slice()
    }
    const finishing = Promise.race([collect(), this.interruption.promise]).finally(() => {
      if (this.finishing === finishing) this.finishing = null
    })
    this.finishing = finishing
    return finishing
  }

  discard(): void {
    if (this.mode === 'discarded') return
    const generation = this.current
    const shouldStop = generation?.state === 'recording' || generation?.state === 'starting'
    const error = this.fatalError ?? new Error('本组录像已取消，请重做本组')
    this.fatalError = error
    this.mode = 'discarded'
    this.current = null
    clearTimeout(this.continuation)
    this.interruption.reject(error)
    if (generation) {
      this.clearTimers(generation)
      generation.start.reject(error)
      generation.video.reject(error)
    }
    if (shouldStop) {
      this.options.onEvent?.('discard_stop')
      try { this.options.camera.stopRecord({}) } catch { /* camera is being replaced */ }
    }
  }

  hasFailedSegment(): boolean { return this.failedSave !== null }

  async retryFailedSegment(): Promise<MotionTrainingRecordedSegment | null> {
    this.checkActive()
    const generation = this.failedSave
    if (!generation) return null
    this.deliver(generation)
    await Promise.race([generation.delivery, this.interruption.promise])
    this.checkActive()
    return generation.segment!
  }

  private startGeneration(): Promise<void> {
    const remaining = (this.options.maxDurationMs ?? Infinity) - this.recordedMs
    if (remaining <= 0) {
      this.mode = 'finishing'
      this.options.onMaxDuration?.(this.options.now())
      return Promise.resolve()
    }
    const generation: Generation = {
      state: 'starting', startedAt: this.options.now(),
      start: deferred<void>(), video: deferred<MotionTrainingRecordedSegment>(), timers: new Set()
    }
    this.current = generation
    this.watch(generation, 'starting')
    try {
      this.options.camera.startRecord({
        timeout: NATIVE_TIMEOUT_SECONDS,
        success: () => {
          if (!this.isCurrent(generation) || generation.state !== 'starting') return
          this.clearTimers(generation)
          generation.startedAt = this.options.now()
          generation.state = 'recording'
          generation.start.resolve()
          if (this.mode === 'finishing') this.stop(generation, 'finish_stop')
          else this.timer(generation, Math.min(SEGMENT_MS, remaining), () => this.stop(generation, 'segment_stop'))
        },
        fail: error => this.fail(generation, '摄像头录像启动失败，请重做本组', error),
        timeoutCallback: result => this.receive(generation, result.tempVideoPath)
      })
    } catch (error) { this.fail(generation, '摄像头录像启动失败，请重做本组', error) }
    return generation.start.promise
  }

  private stop(generation: Generation, event: 'segment_stop' | 'finish_stop'): void {
    // A Finish during start waits for its acknowledgement; a Finish during stop
    // subscribes to the same result instead of issuing another native stop.
    if (!this.isCurrent(generation) || generation.state !== 'recording') return
    this.clearTimers(generation)
    generation.state = 'stopping'
    generation.stoppedAt = this.options.now()
    this.options.onEvent?.(event)
    this.watch(generation, 'stopping')
    try {
      this.options.camera.stopRecord({
        success: result => this.receive(generation, result.tempVideoPath),
        fail: error => this.fail(generation, '摄像头未能结束本组录像，请重做本组', error)
      })
    } catch (error) { this.fail(generation, '摄像头未能结束本组录像，请重做本组', error) }
  }

  private receive(generation: Generation, path: string): void {
    if (!this.isCurrent(generation) || generation.state === 'stopped') return
    if (!path || generation.state === 'starting') {
      this.fail(generation, '摄像头未返回有效录像，请重做本组', { errMsg: 'stopRecord:fail invalid response' })
      return
    }
    this.clearTimers(generation)
    generation.stoppedAt ??= this.options.now()
    generation.state = 'stopped'
    generation.segment = {
      savedFilePath: path,
      durationMs: Math.max(1, generation.stoppedAt - generation.startedAt)
    }
    this.deliver(generation)
    generation.video.resolve(generation.segment)
    void generation.delivery!.then(() => {
      if (!this.isCurrent(generation) || this.mode !== 'recording') return
      // Leave the SDK callback and let its recording-state cleanup finish.
      this.continuation = setTimeout(() => {
        if (this.isCurrent(generation) && this.mode === 'recording') void this.startGeneration().catch(() => undefined)
      }, 0)
    }, () => undefined)
  }

  private deliver(generation: Generation): void {
    const segment = generation.segment!
    generation.delivery = Promise.resolve().then(() => {
      this.checkActive()
      return this.options.onSegment(segment.savedFilePath, segment.durationMs)
    }).then(() => {
      this.checkActive()
      if (!this.segments.some(item => item.savedFilePath === segment.savedFilePath)) {
        this.segments.push(segment)
        this.recordedMs += segment.durationMs
      }
      if (this.failedSave === generation) this.failedSave = null
      // The limit also wins when Finish joined a boundary stop, or when a
      // failed final save was retried. A limit is never a completed set.
      if (this.recordedMs >= (this.options.maxDurationMs ?? Infinity)) {
        const error = new Error('已达到单组录像时限，本组未完成，请休息后重做本组')
        this.fatalError = error
        this.mode = 'failed'
        this.interruption.reject(error)
        this.options.onEvent?.('duration_limit')
        this.options.onMaxDuration?.(generation.stoppedAt!)
        throw error
      }
    }).catch(error => {
      if (this.isCurrent(generation)) this.failedSave = generation
      throw error
    })
    void generation.delivery.catch(() => undefined)
  }

  private watch(generation: Generation, phase: 'starting' | 'stopping'): void {
    this.slowPhase = null
    this.timer(generation, SLOW_MS, () => {
      this.slowPhase = phase
      this.options.onStopSlow?.(phase)
    })
    this.timer(generation, DEADLINE_MS, () => {
      this.options.onEvent?.(phase === 'starting' ? 'start_timeout' : 'stop_timeout')
      this.fail(generation, phase === 'starting'
        ? '摄像头启动超时，请重做本组' : '摄像头返回录像超时，请重做本组',
      { errMsg: `${phase === 'starting' ? 'startRecord' : 'stopRecord'}:fail timeout` })
    })
  }

  private fail(generation: Generation, message: string, nativeError: unknown): void {
    if (!this.isCurrent(generation) || generation.state === 'stopped') return
    const error = new Error(message)
    this.fatalError = error
    this.mode = 'failed'
    generation.state = 'failed'
    this.clearTimers(generation)
    clearTimeout(this.continuation)
    generation.start.reject(error)
    generation.video.reject(error)
    this.interruption.reject(error)
    this.options.onEvent?.('recording_failed')
    try { this.options.onNativeError?.(nativeError) } catch { /* diagnostics must not block recovery */ }
    this.options.onFatalError?.(error)
  }

  private timer(generation: Generation, delay: number, callback: () => void): void {
    const timer = setTimeout(() => {
      generation.timers.delete(timer)
      if (this.isCurrent(generation)) callback()
    }, delay)
    generation.timers.add(timer)
  }

  private clearTimers(generation: Generation): void {
    this.slowPhase = null
    generation.timers.forEach(timer => clearTimeout(timer))
    generation.timers.clear()
  }

  private isCurrent(generation: Generation): boolean {
    return this.current === generation && !this.fatalError
  }

  private checkActive(): void {
    if (this.fatalError) throw this.fatalError
  }
}
