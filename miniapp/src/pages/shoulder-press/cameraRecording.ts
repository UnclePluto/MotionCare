export type CameraRecordResult = {
  tempVideoPath: string
}

export type CameraStartRecordOptions = {
  success: () => void
  fail: (reason: { errMsg?: string }) => void
  timeoutCallback: (result: CameraRecordResult) => void
}

type StartCameraRecordingOptions = {
  startRecord: (options: CameraStartRecordOptions) => void
  timeoutCallback: (result: CameraRecordResult) => void
  retryDelaysMs: number[]
  sleep: (milliseconds: number) => Promise<void>
  isCancelled: () => boolean
}

function startOnce(
  startRecord: StartCameraRecordingOptions['startRecord'],
  timeoutCallback: StartCameraRecordingOptions['timeoutCallback'],
): Promise<void> {
  return new Promise((resolve, reject) => {
    startRecord({
      success: resolve,
      timeoutCallback,
      fail: (reason) => reject(new Error(reason.errMsg || '无法开始录像')),
    })
  })
}

export async function startCameraRecordingWithRetry(
  options: StartCameraRecordingOptions,
): Promise<void> {
  let attempt = 0
  while (true) {
    if (options.isCancelled()) throw new Error('录像启动已取消')
    try {
      await startOnce(options.startRecord, options.timeoutCallback)
      return
    } catch (reason) {
      if (options.isCancelled()) throw new Error('录像启动已取消')
      if (attempt >= options.retryDelaysMs.length) throw reason
      await options.sleep(options.retryDelaysMs[attempt])
      attempt += 1
    }
  }
}
