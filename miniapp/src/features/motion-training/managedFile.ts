import { releaseMotionTrainingLocalFile } from './localFile'
import { isUsableTempVideoPath, type StorageLike } from './session'

type SaveFile = (options: { tempFilePath: string }) => Promise<unknown>
// Retain a moved path if its manifest checkpoint fails, so a foreground retry
// never tries to move the now-invalid source again.
const uncheckpointedMoves = new Map<string, string>()
const activeMoves = new Map<string, Promise<string>>()
const MOVE_JOURNAL_KEY = 'motioncare.motionTraining.fileMoves.v1'
function moves(storage?: StorageLike): Record<string, string> {
  const value = storage?.getStorageSync(MOVE_JOURNAL_KEY)
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  return Object.fromEntries(Object.entries(value).filter(([from, to]) => isUsableTempVideoPath(from) && isUsableTempVideoPath(to)))
}
export const resolveManagedMotionTrainingPath = (path: string, storage?: StorageLike) => uncheckpointedMoves.get(path) ?? moves(storage)[path] ?? path
export const protectedManagedMotionTrainingPaths = (storage: StorageLike) => new Set([...uncheckpointedMoves.values(), ...Object.values(moves(storage))])

export async function saveManagedMotionTrainingFile(path: string, save: SaveFile, checkpoint: (path: string) => void, storage?: StorageLike): Promise<string> {
  let savedPath = uncheckpointedMoves.get(path) ?? moves(storage)[path]
  let active: Promise<string>
  if (!savedPath) {
    const existing = activeMoves.get(path)
    if (existing) active = existing
    else {
      active = (async () => {
        const result = await save({ tempFilePath: path })
        if (!result || typeof result !== 'object' || !('savedFilePath' in result) || typeof result.savedFilePath !== 'string' || !result.savedFilePath.trim()) throw new Error('录像转存未返回有效路径，请重试')
        uncheckpointedMoves.set(path, result.savedFilePath)
        return result.savedFilePath
      })()
      activeMoves.set(path, active)
      const own = active
      const clear = () => { if (activeMoves.get(path) === own) activeMoves.delete(path) }
      void active.then(clear, clear)
    }
  } else active = Promise.resolve(savedPath)
  // Keep the continuation alive after a deadline: a late native move must still
  // checkpoint its new path, even when the page has stopped waiting for it.
  const checked = active.then(newPath => {
    try { storage?.setStorageSync(MOVE_JOURNAL_KEY, { ...moves(storage), [path]: newPath }) } catch { /* Still attempt the owning manifest. */ }
    checkpoint(newPath)
    uncheckpointedMoves.delete(path)
    try {
      const journal = moves(storage)
      delete journal[path]
      if (Object.keys(journal).length) storage?.setStorageSync(MOVE_JOURNAL_KEY, journal)
      else storage?.removeStorageSync(MOVE_JOURNAL_KEY)
    } catch { /* A stale journal is recoverable and must not roll back the manifest. */ }
    return newPath
  })
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([checked, new Promise<never>((_resolve, reject) => {
      timer = setTimeout(() => reject(Object.assign(new Error('录像转存超时，请重试'), { errMsg: 'saveFile:fail timeout' })), 10000)
    })])
  } finally { clearTimeout(timer) }
}

export async function releaseManagedMotionTrainingFile(
  file: Parameters<typeof releaseMotionTrainingLocalFile>[0] & { onMoved: (path: string) => void; onSave?: (event: 'save_call' | 'save_success' | 'save_failure', error?: unknown) => void },
  getFileSystem: Parameters<typeof releaseMotionTrainingLocalFile>[1],
  save: SaveFile,
  storage?: StorageLike
): Promise<{ removed: boolean; filePath: string }> {
  let permissionDenied = false
  const moved = resolveManagedMotionTrainingPath(file.filePath, storage) !== file.filePath
  const removed = moved ? false : await releaseMotionTrainingLocalFile({ ...file, onError: error => {
    const value = error as { errMsg?: string; message?: string } | undefined
    permissionDenied = /permission|denied|not permitted/i.test(value?.errMsg ?? value?.message ?? '')
    file.onError?.(error)
  } }, getFileSystem)
  if (removed || (file.localFileState === 'saved' && !moved) || (!permissionDenied && !moved)) return { removed, filePath: file.filePath }
  const trace = (event: 'save_call' | 'save_success' | 'save_failure', error?: unknown) => {
    try { file.onSave?.(event, error) } catch { /* isolated */ }
  }
  trace('save_call')
  let filePath: string
  try {
    filePath = await saveManagedMotionTrainingFile(file.filePath, save, path => {
      file.onMoved(path)
      trace('save_success')
    }, storage)
  } catch (error) { trace('save_failure', error); throw error }
  return { filePath, removed: await releaseMotionTrainingLocalFile({ ...file, filePath, localFileState: 'saved' }, getFileSystem) }
}
