export type MotionTrainingLocalFileState = 'temporary' | 'save_failed' | 'saved'

export async function saveTemporaryMotionTrainingSegmentForRetry(
  input: {
    filePath: string
    localFileState: MotionTrainingLocalFileState
  },
  saveFile: (options: { tempFilePath: string }) => Promise<{ savedFilePath?: string }>
): Promise<{
  filePath: string
  localFileState: MotionTrainingLocalFileState
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
