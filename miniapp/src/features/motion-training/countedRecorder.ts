import type { CameraContext } from './recorder'

export type CompletionReason = 'manual' | 'time_limit'
export type CountedVideo = { path: string; durationMs: number }
export type CountedRecorderEvent = 'finish_stop' | 'discard_stop' | 'start_timeout' | 'stop_timeout' | 'recording_failed' | 'duration_limit'
const LIMIT_MS = 300000
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (error: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  void promise.catch(() => undefined)
  return { promise, resolve, reject }
}
type Options = {
  camera: CameraContext; now: () => number
  onVideo: (path: string, durationMs: number) => Promise<void> | void
  onEnding: (endedAtMs: number, reason: CompletionReason) => void
  onNativeError?: (error: unknown) => void
  onFatalError?: (error: Error) => void
  onStopSlow?: (phase: 'starting' | 'stopping') => void
  onEvent?: (event: CountedRecorderEvent) => void
}

/** One attempt, one native recording, one file. SDK owns the five-minute stop. */
export class CountedTrainingRecorder {
  private phase: 'idle' | 'starting' | 'recording' | 'stopping' | 'stopped' | 'completed' | 'failed' = 'idle'
  private readonly started = deferred<void>()
  private readonly video = deferred<CountedVideo>()
  private readonly interruption = deferred<never>()
  private readonly timers = new Set<ReturnType<typeof setTimeout>>()
  private startedAt = 0
  private endedAt?: number
  private requestedReason?: CompletionReason
  private fatalError?: Error
  private result?: CountedVideo
  private delivery?: Promise<void>
  private deliveryFailed = false
  private finishing?: Promise<CountedVideo>
  private slowPhase?: 'starting' | 'stopping'
  constructor(private readonly options: Options) {}

  get startedAtMs(): number { return this.startedAt }

  start(): Promise<void> {
    if (this.fatalError) return Promise.reject(this.fatalError)
    if (this.phase !== 'idle') return this.started.promise
    this.phase = 'starting'; this.watch('starting')
    try {
      this.options.camera.startRecord({ timeout: 300,
        success: () => {
          if (this.phase !== 'starting' || this.fatalError) return
          this.clearTimers(); this.startedAt = this.options.now(); this.phase = 'recording'
          this.started.resolve()
          this.timer(LIMIT_MS, () => this.end('time_limit'))
          if (this.requestedReason) this.end(this.requestedReason)
        },
        fail: error => this.fail('摄像头录像启动失败，请重做本组', error),
        timeoutCallback: value => {
          if (this.fatalError || this.result) return
          if (this.phase === 'recording' && this.options.now() >= this.startedAt + LIMIT_MS) this.end('time_limit')
          if (this.phase !== 'stopping') {
            this.fail('录像已中断，请重做本组', { errMsg: 'recording interrupted' }); return
          }
          this.receive(value.tempVideoPath)
        }
      })
    } catch (error) { this.fail('摄像头录像启动失败，请重做本组', error) }
    return this.started.promise
  }

  finish(reason: CompletionReason = 'manual'): Promise<CountedVideo> {
    if (this.fatalError) return Promise.reject(this.fatalError)
    if (this.phase === 'completed') return Promise.resolve(this.result!)
    if (this.phase === 'idle') return Promise.reject(new Error('本组录像尚未开始'))
    if (this.finishing) {
      if (this.slowPhase) this.options.onStopSlow?.(this.slowPhase)
      return this.finishing
    }
    this.requestedReason ??= reason
    if (this.phase === 'recording') this.end(reason)
    if (this.slowPhase) this.options.onStopSlow?.(this.slowPhase)
    const collect = async () => {
      const video = await this.video.promise
      await this.delivery
      this.checkActive(); this.phase = 'completed'
      return video
    }
    const promise = Promise.race([collect(), this.interruption.promise]).finally(() => {
      if (this.finishing === promise) this.finishing = undefined
    })
    this.finishing = promise
    return promise
  }

  private end(reason: CompletionReason): void {
    if (this.phase !== 'recording' || this.fatalError) return
    const deadline = this.startedAt + LIMIT_MS
    const atLimit = this.options.now() >= deadline
    // Before the actual deadline only a manual request may finish a recording.
    if (reason === 'time_limit' && !atLimit) return
    this.clearTimers(); this.phase = 'stopping'
    this.endedAt = atLimit ? deadline : Math.max(this.startedAt + 1, this.options.now())
    this.watch('stopping')
    this.options.onEnding(this.endedAt, atLimit ? 'time_limit' : 'manual')
    if (atLimit) { this.options.onEvent?.('duration_limit'); return }
    this.options.onEvent?.('finish_stop')
    try {
      this.options.camera.stopRecord({
        success: value => this.receive(value.tempVideoPath),
        fail: error => this.fail('摄像头未能结束录像，请重做本组', error)
      })
    } catch (error) { this.fail('摄像头未能结束录像，请重做本组', error) }
  }

  private receive(path: string): void {
    if (this.fatalError || this.result) return
    if (!path || this.phase !== 'stopping' || this.endedAt === undefined) {
      this.fail('摄像头未返回有效录像，请重做本组', { errMsg: 'invalid recording result' }); return
    }
    this.clearTimers(); this.phase = 'stopped'
    this.result = { path, durationMs: Math.max(1, this.endedAt - this.startedAt) }
    this.deliver(); this.video.resolve(this.result)
  }
  private deliver(): void {
    this.deliveryFailed = false
    this.delivery = Promise.resolve().then(() => {
      this.checkActive(); return this.options.onVideo(this.result!.path, this.result!.durationMs)
    }).then(() => { this.checkActive(); this.deliveryFailed = false }).catch(error => {
      if (!this.fatalError) this.deliveryFailed = true
      throw error
    })
    void this.delivery.catch(() => undefined)
  }
  hasFailedVideo(): boolean { return this.deliveryFailed }
  async retryVideo(): Promise<void> {
    this.checkActive()
    if (!this.deliveryFailed) return
    this.deliver()
    await Promise.race([this.delivery!, this.interruption.promise]); this.checkActive()
  }
  discard(): void {
    if (this.fatalError) return
    const shouldStop = this.phase === 'recording' || this.phase === 'starting'
    this.fatalError = new Error('本组录像已取消，请重做本组'); this.phase = 'failed'; this.clearTimers()
    this.started.reject(this.fatalError); this.video.reject(this.fatalError); this.interruption.reject(this.fatalError)
    if (shouldStop) {
      this.options.onEvent?.('discard_stop')
      try { this.options.camera.stopRecord({}) } catch { /* camera is being replaced */ }
    }
  }
  private watch(phase: 'starting' | 'stopping'): void {
    this.timer(10000, () => { this.slowPhase = phase; this.options.onStopSlow?.(phase) })
    this.timer(30000, () => {
      this.options.onEvent?.(phase === 'starting' ? 'start_timeout' : 'stop_timeout')
      this.fail(phase === 'starting' ? '摄像头启动超时，请重做本组' : '摄像头返回录像超时，请重做本组', { errMsg: phase + ':fail timeout' })
    })
  }
  private fail(message: string, nativeError: unknown): void {
    if (this.fatalError || this.result) return
    const error = new Error(message); this.fatalError = error; this.phase = 'failed'; this.clearTimers()
    this.started.reject(error); this.video.reject(error); this.interruption.reject(error)
    this.options.onEvent?.('recording_failed')
    try { this.options.onNativeError?.(nativeError) } catch { /* diagnostics do not block recovery */ }
    this.options.onFatalError?.(error)
  }
  private timer(delay: number, fn: () => void): void {
    const timer = setTimeout(() => { this.timers.delete(timer); if (!this.fatalError) fn() }, delay)
    this.timers.add(timer)
  }
  private clearTimers(): void {
    this.timers.forEach(clearTimeout); this.timers.clear(); this.slowPhase = undefined
  }
  private checkActive(): void { if (this.fatalError) throw this.fatalError }
}
