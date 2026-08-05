export type ShoulderPressLocalFileState = 'temporary' | 'save_failed' | 'saved'

export async function saveTemporaryShoulderPressSegmentForRetry(
  input: {
    filePath: string
    localFileState: ShoulderPressLocalFileState
  },
  saveFile: (options: { tempFilePath: string }) => Promise<{ savedFilePath?: string }>
): Promise<{
  filePath: string
  localFileState: ShoulderPressLocalFileState
}> {
  if (input.localFileState !== 'temporary') return input

  try {
    const saved = await saveFile({ tempFilePath: input.filePath })
    if (typeof saved.savedFilePath === 'string' && saved.savedFilePath.trim()) {
      return {
        filePath: saved.savedFilePath,
        localFileState: 'saved'
      }
    }
  } catch {
    // 上传错误仍是主错误；持久化失败只改变本地恢复能力。
  }

  return {
    filePath: input.filePath,
    localFileState: 'save_failed'
  }
}
