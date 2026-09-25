export type MotionTrainingLocalFileState = 'temporary' | 'save_failed' | 'saved'

type RemoveOptions = { filePath: string; success: () => void; fail: (error: unknown) => void }
type LocalFileSystem = {
  unlink: (options: RemoveOptions) => void
  removeSavedFile: (options: RemoveOptions) => void
  access?: (options: { path: string; success: () => void; fail: (error: unknown) => void }) => void
}

export const LOCAL_FILE_CLEANUP_TIMEOUT_MS = 10000

function fileAlreadyMissing(error: unknown): boolean {
  const value = error && typeof error === 'object' ? error as { errMsg?: unknown; message?: unknown } : {}
  const message = typeof value.errMsg === 'string' ? value.errMsg : typeof value.message === 'string' ? value.message : ''
  return /ENOENT|no such file|file (?:not exist|does not exist|not found)|文件不存在|文件未找到/i.test(message)
}

export function releaseMotionTrainingLocalFile(
  file: { filePath: string; localFileState?: MotionTrainingLocalFileState; onError?: (error: unknown) => void; onSuccess?: () => void;
    onAccess?: (event: 'access_call' | 'access_exists' | 'access_failure', error?: unknown) => void },
  getFileSystem: () => LocalFileSystem
): Promise<boolean> {
  return new Promise(resolve => {
    let settled = false
    let checking = false
    const report = (error: unknown) => {
      try { file.onError?.(error) } catch { /* Diagnostics cannot affect cleanup. */ }
    }
    const finish = (removed: boolean) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      if (removed) {
        try { file.onSuccess?.() } catch { /* Diagnostics cannot affect cleanup. */ }
      }
      resolve(removed)
    }
    const timer = setTimeout(() => {
      if (settled) return
      report({ errMsg: 'local cleanup:fail timeout' })
      finish(false)
    }, LOCAL_FILE_CLEANUP_TIMEOUT_MS)
    const accessEvent = (event: 'access_call' | 'access_exists' | 'access_failure', error?: unknown) => {
      try { file.onAccess?.(event, error) } catch { /* isolated */ }
    }
    let fs: LocalFileSystem
    const success = () => {
      finish(true)
    }
    const fail = (error: unknown) => {
      if (settled || checking) return
      report(error)
      if (fileAlreadyMissing(error)) { success(); return }
      if (!fs?.access) { finish(false); return }
      checking = true
      accessEvent('access_call')
      const accessFailure = (accessError: unknown) => {
        if (settled) return
        accessEvent('access_failure', accessError)
        finish(fileAlreadyMissing(accessError))
      }
      try {
        fs.access({ path: file.filePath, success: () => {
          if (settled) return
          accessEvent('access_exists')
          finish(false)
        }, fail: accessFailure })
      } catch (accessError) { accessFailure(accessError) }
    }
    const options = { filePath: file.filePath, success, fail }
    try {
      fs = getFileSystem()
      if (file.localFileState === 'saved') fs.removeSavedFile(options)
      else fs.unlink(options)
    } catch (error) { fail(error) }
  })
}

export async function saveTemporaryMotionTrainingSegmentForRetry(
  input: {
    filePath: string
    localFileState: MotionTrainingLocalFileState
    onError?: (error: unknown) => void
  },
  saveFile: (options: { tempFilePath: string }) => Promise<unknown>
): Promise<{
  filePath: string
  localFileState: MotionTrainingLocalFileState
}> {
  if (input.localFileState !== 'temporary') return input

  try {
    const saved = await saveFile({ tempFilePath: input.filePath })
    if (saved && typeof saved === 'object' && 'savedFilePath' in saved
      && typeof saved.savedFilePath === 'string' && saved.savedFilePath.trim()) {
      return {
        filePath: saved.savedFilePath,
        localFileState: 'saved'
      }
    }
    throw new Error('invalid saved file response')
  } catch (error) {
    try { input.onError?.(error) } catch { /* isolated */ }
    // 上传错误仍是主错误；持久化失败只改变本地恢复能力。
  }

  return {
    filePath: input.filePath,
    localFileState: 'save_failed'
  }
}
