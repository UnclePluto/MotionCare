export const WECHAT_SAVED_FILE_CAPACITY_BYTES = 100 * 1024 * 1024
export const MOTION_TRAINING_START_REQUIRED_FREE_BYTES = 65 * 1024 * 1024

export type MotionTrainingSavedFile = {
  filePath: string
  size: number
  createTime?: number
}

export type MotionTrainingStorageGuardResult =
  | { kind: 'pending_session' }
  | { kind: 'cancelled' }
  | { kind: 'ready'; usedBytes: number; availableBytes: number }
  | { kind: 'blocked'; usedBytes: number; availableBytes: number }

type StorageGuardInput = {
  hasPendingSession: () => boolean
  listSavedFiles: () => Promise<MotionTrainingSavedFile[]>
  removeSavedFile: (filePath: string) => Promise<void>
  isActive: () => boolean
}

const normalizedSize = (value: number) => (
  Number.isFinite(value) && value > 0 ? Math.floor(value) : 0
)

function usedSavedBytes(files: MotionTrainingSavedFile[]): number {
  return Math.min(
    WECHAT_SAVED_FILE_CAPACITY_BYTES,
    files.reduce((total, file) => total + normalizedSize(file.size), 0)
  )
}

export async function cleanupAndCheckMotionTrainingStorage(
  input: StorageGuardInput
): Promise<MotionTrainingStorageGuardResult> {
  if (input.hasPendingSession()) return { kind: 'pending_session' }

  const before = await input.listSavedFiles()
  if (!input.isActive()) return { kind: 'cancelled' }

  await Promise.allSettled(before.map((file) => input.removeSavedFile(file.filePath)))
  if (!input.isActive()) return { kind: 'cancelled' }

  const after = await input.listSavedFiles()
  if (!input.isActive()) return { kind: 'cancelled' }

  const usedBytes = usedSavedBytes(after)
  const availableBytes = WECHAT_SAVED_FILE_CAPACITY_BYTES - usedBytes
  return {
    kind: availableBytes >= MOTION_TRAINING_START_REQUIRED_FREE_BYTES ? 'ready' : 'blocked',
    usedBytes,
    availableBytes
  }
}
