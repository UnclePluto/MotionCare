type RecordStartOptions = {
  success?: () => void
  fail?: () => void
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

const MIN_PAUSE_SEGMENT_MS = 2000
const TIMEOUT_SEGMENT_MS = 30000

export class ShoulderPressRecorder {
  private readonly camera: CameraContext
  private readonly now: () => number
  private readonly onSegment: (path: string, durationMs: number) => Promise<void> | void
  private readonly onPause?: () => void
  private generation = 0
  private mode: RecorderMode = 'idle'
  private startedAt = 0
  private readonly deliveredPaths = new Set<string>()
  private readonly deliveredSegments: ShoulderPressRecordedSegment[] = []

  constructor(input: {
    camera: CameraContext
    now: () => number
    onSegment: (path: string, durationMs: number) => Promise<void> | void
    onPause?: () => void
  }) {
    this.camera = input.camera
    this.now = input.now
    this.onSegment = input.onSegment
    this.onPause = input.onPause
  }

  start(): Promise<void> {
    if (this.mode === 'recording') return Promise.resolve()
    this.mode = 'recording'
    return this.startGeneration()
  }

  pause(): Promise<ShoulderPressRecordedSegment | null> {
    if (this.mode !== 'recording') return Promise.resolve(null)
    this.mode = 'pausing'
    const generation = this.generation
    return this.stopCurrent(generation, true).finally(() => {
      this.onPause?.()
      if (this.mode === 'pausing') this.mode = 'idle'
    })
  }

  async finish(): Promise<ShoulderPressRecordedSegment[]> {
    if (this.mode !== 'recording') return this.deliveredSegments.slice()
    this.mode = 'finishing'
    const generation = this.generation
    await this.stopCurrent(generation, false)
    if (this.mode === 'finishing') this.mode = 'idle'
    return this.deliveredSegments.slice()
  }

  private startGeneration(): Promise<void> {
    const generation = this.generation + 1
    this.generation = generation
    this.startedAt = this.now()

    return new Promise((resolve, reject) => {
      this.camera.startRecord({
        success: () => resolve(),
        fail: () => {
          this.mode = 'idle'
          reject(new Error('摄像头录像启动失败，请检查权限后重试'))
        },
        timeoutCallback: (result) => {
          void this.handleTimeout(generation, result.tempVideoPath)
        }
      })
    })
  }

  private async handleTimeout(generation: number, path: string): Promise<void> {
    if (generation !== this.generation || this.mode !== 'recording') return
    const durationMs = this.durationSinceStart(TIMEOUT_SEGMENT_MS)
    await this.startGeneration()
    await this.deliver(path, durationMs)
  }

  private stopCurrent(generation: number, discardShortPause: boolean): Promise<ShoulderPressRecordedSegment | null> {
    return new Promise((resolve, reject) => {
      this.camera.stopRecord({
        success: (result) => {
          const durationMs = this.durationSinceStart(0)
          if (generation !== this.generation && this.deliveredPaths.has(result.tempVideoPath)) {
            resolve(null)
            return
          }
          if (discardShortPause && durationMs < MIN_PAUSE_SEGMENT_MS) {
            resolve(null)
            return
          }
          this.deliver(result.tempVideoPath, durationMs)
            .then((segment) => resolve(segment))
            .catch((error: unknown) => reject(error instanceof Error ? error : new Error('录像分段保存失败')))
        },
        fail: () => reject(new Error('录像停止失败，请稍后重试'))
      })
    })
  }

  private durationSinceStart(fallbackMs: number): number {
    const durationMs = Math.max(0, Math.round(this.now() - this.startedAt))
    return durationMs > 0 ? durationMs : fallbackMs
  }

  private async deliver(path: string, durationMs: number): Promise<ShoulderPressRecordedSegment | null> {
    if (!path || this.deliveredPaths.has(path)) return null
    this.deliveredPaths.add(path)
    const segment = { savedFilePath: path, durationMs }
    this.deliveredSegments.push(segment)
    await this.onSegment(path, durationMs)
    return segment
  }
}
