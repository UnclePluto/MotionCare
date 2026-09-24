export type MotionTrainingLocalFileState = 'temporary' | 'save_failed' | 'saved'

type RemoveOptions = { filePath: string; success: () => void; fail: (error: unknown) => void }
type LocalFileSystem = { unlink: (options: RemoveOptions) => void; removeSavedFile: (options: RemoveOptions) => void }

function fileAlreadyMissing(error: unknown): boolean {
  const value = error && typeof error === 'object' ? error as { errMsg?: unknown; message?: unknown } : {}
  const message = typeof value.errMsg === 'string' ? value.errMsg : typeof value.message === 'string' ? value.message : ''
  return /ENOENT|no such file|file (?:not exist|does not exist|not found)|文件不存在|文件未找到/i.test(message)
}

export function releaseMotionTrainingLocalFile(
  file: { filePath: string; localFileState?: MotionTrainingLocalFileState },
  getFileSystem: () => LocalFileSystem
): Promise<boolean> {
  return new Promise(resolve => {
    const options = { filePath: file.filePath, success: () => resolve(true), fail: (error: unknown) => resolve(fileAlreadyMissing(error)) }
    try {
      const fs = getFileSystem()
      if (file.localFileState === 'saved') fs.removeSavedFile(options)
      else fs.unlink(options)
    } catch (error) { resolve(fileAlreadyMissing(error)) }
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
