import Taro from '@tarojs/taro'

export type CountedVideoFile = { path: string; durationMs: number; sizeBytes: number; persistence: 'saved' | 'temporary' }

/** Remember moves even when the following metadata read fails. Never move an uploading file. */
export function createCountedFilePreparer(onSaved?: (path: string) => void) {
  const prepared = new Map<string, Pick<CountedVideoFile, 'path' | 'persistence'>>()
  return async (tempPath: string, durationMs: number): Promise<CountedVideoFile> => {
    let file = prepared.get(tempPath)
    if (!file) {
      try {
        const saved = await Taro.saveFile({ tempFilePath: tempPath })
        if (!('savedFilePath' in saved) || !saved.savedFilePath) throw new Error('保存未返回路径')
        file = { path: saved.savedFilePath, persistence: 'saved' }
        onSaved?.(file.path)
      } catch { file = { path: tempPath, persistence: 'temporary' } }
      prepared.set(tempPath, file)
    }
    const info = await Taro.getFileInfo({ filePath: file.path })
    if (!('size' in info) || !Number.isSafeInteger(info.size) || info.size <= 0) throw new Error('录像文件无法读取，请重试保存或重做本组')
    return { ...file, sizeBytes: info.size, durationMs }
  }
}

function fileAlreadyMissing(error: unknown): boolean {
  const value = error && typeof error === 'object' ? error as { errMsg?: unknown; message?: unknown } : {}
  const message = typeof value.errMsg === 'string' ? value.errMsg : typeof value.message === 'string' ? value.message : ''
  return /ENOENT|no such file|file (?:not exist|does not exist|not found)|文件不存在|文件未找到/i.test(message)
}

export function releaseCountedFile(file: Pick<CountedVideoFile, 'path' | 'persistence'>): Promise<boolean> {
  return new Promise(resolve => {
    const options = { filePath: file.path, success: () => resolve(true), fail: (error: unknown) => resolve(fileAlreadyMissing(error)) }
    try {
      const fs = Taro.getFileSystemManager()
      if (file.persistence === 'saved') fs.removeSavedFile(options)
      else fs.unlink(options)
    } catch (error) { resolve(fileAlreadyMissing(error)) }
  })
}
