export const GAME_SESSION_SUBPACKAGE_NAME = 'pages/game-session'

export type GameSubpackageLoadResult = 'loaded' | 'unsupported'

export type SubpackageProgressEvent = {
  progress: number
  totalBytesWritten?: number
  totalBytesExpectedToWrite?: number
}

type RawSubpackageProgressEvent = {
  progress?: number
  totalBytesWritten?: number
  totalBytesExpectedToWrite?: number
}

type LoadSubpackageOptions = {
  name: string
  success: () => void
  fail: (error: { errMsg?: string }) => void
}

type LoadSubpackageTask = {
  onProgressUpdate?: (listener: (event: RawSubpackageProgressEvent) => void) => void
}

export type WechatSubpackageRuntime = {
  loadSubpackage?: (options: LoadSubpackageOptions) => LoadSubpackageTask
}

export function gameSessionUrl(actionId: number): string {
  return `/pages/game-session/index?actionId=${encodeURIComponent(String(actionId))}`
}

function normalizeProgress(value: number | undefined): number {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value as number)))
}

function currentWechatRuntime(): WechatSubpackageRuntime | undefined {
  return (globalThis as { wx?: WechatSubpackageRuntime }).wx
}

export function loadGameSessionSubpackage(
  onProgress: (event: SubpackageProgressEvent) => void,
  runtime: WechatSubpackageRuntime | undefined = currentWechatRuntime()
): Promise<GameSubpackageLoadResult> {
  if (!runtime?.loadSubpackage) {
    onProgress({ progress: 100 })
    return Promise.resolve('unsupported')
  }

  return new Promise((resolve, reject) => {
    const task = runtime.loadSubpackage?.({
      name: GAME_SESSION_SUBPACKAGE_NAME,
      success: () => {
        onProgress({ progress: 100 })
        resolve('loaded')
      },
      fail: (error) => {
        reject(new Error(error.errMsg || '游戏资源加载失败'))
      },
    })

    task?.onProgressUpdate?.((event) => {
      onProgress({
        progress: normalizeProgress(event.progress),
        totalBytesWritten: event.totalBytesWritten,
        totalBytesExpectedToWrite: event.totalBytesExpectedToWrite,
      })
    })
  })
}
