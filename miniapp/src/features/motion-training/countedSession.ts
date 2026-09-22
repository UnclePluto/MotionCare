import Taro from '@tarojs/taro'
import { request } from '../../api/client'
import { getPatientAppToken } from '../../auth/token'
import { fetchPatientHomeData } from '../../demo/patientAppData'
import { isDemoSession } from '../../demo/session'
import { createClientSessionId } from './session'
import { createVideoSession, finalizeVideoSession, getVideoSessionStatus, uploadVideoSegment } from './api'
import type { MotionTrainingAction } from './pageState'

export const COUNTED_QUEUE_KEY = 'motioncare.countedMotionQueue.v1'
export type CountedSegment = { path: string; durationMs: number; sizeBytes: number }
export type CountedAttempt = {
  id: string; index: number; startedAt: string; endedAt?: string; completed: boolean
  abandoned?: boolean; segments: CountedSegment[]; uploaded?: boolean; videoId?: number
  uploadId: string; error?: string
}
export type CountedSession = {
  id: string; owner: number; actionId: number; actionName: string; plannedSets: number
  repetitions: number; countUnit: 'total' | 'per_side'; startedAt: string; trainingDate: string
  attempts: CountedAttempt[]; serverId?: number; exited?: boolean
}
type Queue = Record<string, CountedSession[]>
export function shanghaiDate(now = Date.now()): string { return new Date(now + 8 * 3600000).toISOString().slice(0, 10) }
function readQueue(): Queue {
  const saved = Taro.getStorageSync(COUNTED_QUEUE_KEY)
  if (!saved) return {}
  // A corrupt queue must never be overwritten or interpreted as permission to delete files.
  if (typeof saved !== 'object' || Array.isArray(saved)) throw new Error('本地录像记录无法读取，请联系指导老师协助保留录像')
  return JSON.parse(JSON.stringify(saved)) as Queue
}
export function countedSessions(owner: number): CountedSession[] { return readQueue()[owner] ?? [] }
export function storeCountedSession(session: CountedSession): void {
  const all = readQueue(); const owned = all[session.owner] ?? []
  const index = owned.findIndex(item => item.id === session.id)
  if (index < 0) owned.push(session); else owned[index] = session
  all[session.owner] = owned
  Taro.setStorageSync(COUNTED_QUEUE_KEY, all)
  notifyQueue()
}
export function updateCountedSession(owner: number, id: string, update: (session: CountedSession) => void): CountedSession {
  const session = countedSessions(owner).find(item => item.id === id)
  if (!session) throw new Error('本地运动记录无法读取')
  update(session); storeCountedSession(session); return session
}
export function completedAttempts(session: CountedSession): CountedAttempt[] { return session.attempts.filter(item => item.completed && !item.abandoned) }
export function protectedCountedPaths(): Set<string> {
  return new Set(Object.values(readQueue()).flatMap(sessions => sessions.flatMap(session => session.attempts.flatMap(a => a.segments.map(s => s.path)))))
}
export function newCountedSession(owner: number, action: MotionTrainingAction, startedAt: string): CountedSession {
  return { id: createClientSessionId(), owner, actionId: action.id, actionName: action.action_name,
    plannedSets: action.sets!, repetitions: action.repetitions!, countUnit: action.count_unit === 'per_side' ? 'per_side' : 'total',
    startedAt, trainingDate: shanghaiDate(Date.parse(startedAt)), attempts: [] }
}
export async function removeCountedFile(filePath: string): Promise<void> {
  await new Promise<void>((resolve) => {
    try { Taro.getFileSystemManager().removeSavedFile({ filePath, success: () => resolve(), fail: () => resolve() }) } catch { resolve() }
  })
}
export async function discardIncomplete(session: CountedSession): Promise<CountedSession> {
  const incomplete = session.attempts.filter(a => !a.completed)
  for (const attempt of incomplete) for (const segment of attempt.segments) await removeCountedFile(segment.path)
  return updateCountedSession(session.owner, session.id, item => {
    for (const attempt of item.attempts) if (!attempt.completed) { attempt.abandoned = true; attempt.segments = [] }
  })
}
export async function checkCountedStorage(): Promise<void> {
  const files = await new Promise<Array<{ size: number }>>((resolve, reject) => {
    Taro.getFileSystemManager().getSavedFileList({ success: result => resolve(result.fileList), fail: reject })
  })
  if (files.reduce((sum, file) => sum + file.size, 0) > 35 * 1024 * 1024) {
    throw new Error('录像空间不足，至少需要 65 MB 可用空间。请先补传已完成组后再开始。')
  }
}

export type CountedUploadState = {
  phase: 'uploading' | 'confirming' | 'retrying' | 'blocked' | 'completed'
  percent: number; bytesPerSecond: number; updatedAt: number; retryAt?: number; failures: number
}
const uploadStates = new Map<string, CountedUploadState>()
let stateToken: string | undefined
function stateKey(owner: number, attemptId: string) {
  const token = getPatientAppToken()
  if (stateToken !== token) { uploadStates.clear(); stateToken = token }
  return `${owner}:${attemptId}`
}
export function countedUploadState(owner: number, attemptId: string) { return uploadStates.get(stateKey(owner, attemptId)) }
const queueListeners = new Set<() => void>()
export function subscribeCountedQueue(listener: () => void) { queueListeners.add(listener); return () => { queueListeners.delete(listener) } }
function notifyQueue() { for (const listener of queueListeners) { try { listener() } catch { /* UI cannot interrupt durable upload */ } } }

const inflight = new Map<number, Promise<void>>()
export function syncCountedQueue(owner: number, automatic = false): Promise<void> {
  const previous = inflight.get(owner); if (previous) return previous
  const token = getPatientAppToken()
  const active = () => token && token === getPatientAppToken() && !isDemoSession()
  const run = async () => {
    if (!active()) return
    for (const initial of countedSessions(owner)) {
      if (!active()) return
      let session = countedSessions(owner).find(s => s.id === initial.id)!
      const pending = completedAttempts(session).filter(a => !a.uploaded)
      if (!pending.length) continue
      for (const original of pending) {
        if (!active()) return
        const key = stateKey(owner, original.id)
        const previousState = uploadStates.get(key)
        if (automatic && (previousState?.phase === 'blocked' || (previousState?.retryAt ?? 0) > Date.now())) continue
        const progress: CountedUploadState = { phase: 'uploading', percent: 0, bytesPerSecond: 0, updatedAt: Date.now(), failures: previousState?.failures ?? 0 }
        uploadStates.set(key, progress)
        try {
          // A later invalid group must not prevent earlier valid groups from uploading.
          const response = await request<{ id: number }>('/patient-app/motion-sessions/recover/', { method: 'POST', data: {
            client_session_id: session.id, prescription_action: session.actionId, started_at: session.startedAt,
            completed_sets: completedAttempts(session).filter(a => a.index <= original.index).map(a => ({ index: a.index, attempt_id: a.id, started_at: a.startedAt, ended_at: a.endedAt }))
          } })
          if (!active()) return
          if (!Number.isInteger(response.id)) throw new Error('运动进度响应无效，请稍后重试')
          session = updateCountedSession(owner, session.id, s => { s.serverId = response.id })
          let attempt = countedSessions(owner).find(s => s.id === session.id)!.attempts.find(a => a.id === original.id)!
          const patch = (change: (a: CountedAttempt) => void) => {
            const latest = updateCountedSession(owner, session.id, s => change(s.attempts.find(a => a.id === original.id)!))
            attempt = latest.attempts.find(a => a.id === original.id)!
          }
          let status = attempt.videoId ? await getVideoSessionStatus(attempt.videoId) : undefined
          if (!active()) return
          if (status && ['expired', 'failed'].includes(status.status)) { patch(a => { a.videoId = undefined; a.uploadId = createClientSessionId() }); status = undefined }
          if (!status) {
            status = await createVideoSession({ actionId: session.actionId, clientSessionId: attempt.uploadId,
              trainingDate: session.trainingDate, trainingStartedAt: attempt.startedAt, expectedDurationSeconds: 1800,
              motionAttemptId: attempt.id })
            if (!active()) return
            patch(a => { a.videoId = status!.video_id })
          }
          const totalBytes = attempt.segments.reduce((sum, segment) => sum + segment.sizeBytes, 0)
          let sentBytes = attempt.segments.reduce((sum, segment, index) => sum + (status!.uploaded_segments?.includes(index) ? segment.sizeBytes : 0), 0)
          progress.percent = totalBytes ? Math.min(100, Math.floor(sentBytes / totalBytes * 100)) : 0
          if (status.status !== 'attached' && !['queued', 'assembling', 'uploading_qiniu'].includes(status.status)) {
            for (let index = 0; index < attempt.segments.length; index++) {
              if (!active()) return
              if (status.uploaded_segments?.includes(index)) continue
              const segment = attempt.segments[index]
              try { await Taro.getFileInfo({ filePath: segment.path }) } catch { throw new Error('本地录像文件已丢失，无法完成上传。请联系指导老师。') }
              if (!active()) return
              const segmentStartedAt = Date.now()
              await uploadVideoSegment({ videoId: status.video_id, clientSessionId: attempt.uploadId, index,
                filePath: segment.path, durationMs: segment.durationMs, sizeBytes: segment.sizeBytes,
                onProgress: (percent, bytesSent) => {
                  if (!active()) return
                  const bytes = Math.min(segment.sizeBytes, Math.max(0, bytesSent ?? segment.sizeBytes * percent / 100))
                  progress.percent = totalBytes ? Math.min(100, Math.floor((sentBytes + bytes) / totalBytes * 100)) : 0
                  progress.updatedAt = Date.now()
                  progress.bytesPerSecond = bytes * 1000 / Math.max(1, Date.now() - segmentStartedAt)
                } })
              sentBytes += segment.sizeBytes
              progress.percent = totalBytes ? Math.min(100, Math.floor(sentBytes / totalBytes * 100)) : 0
            }
            if (!active()) return
            progress.phase = 'confirming'; progress.percent = 100; progress.bytesPerSecond = 0
            status = await finalizeVideoSession({ videoId: status.video_id, clientSessionId: attempt.uploadId,
              segmentCount: attempt.segments.length, actualDurationSeconds: Math.max(1, Math.round(attempt.segments.reduce((sum, p) => sum + p.durationMs, 0) / 1000)),
              trainingEndedAt: attempt.endedAt, note: '' })
          }
          if (!active()) return
          if (status.status === 'attached') {
            // Persist the server acknowledgement before releasing any original file.
            progress.phase = 'completed'; progress.percent = 100; progress.bytesPerSecond = 0; progress.failures = 0
            patch(a => { a.uploaded = true; a.error = undefined })
            for (const segment of attempt.segments) await removeCountedFile(segment.path)
            patch(a => { a.segments = [] })
          } else {
            progress.phase = 'confirming'; progress.percent = 100; progress.bytesPerSecond = 0; progress.retryAt = Date.now() + 2000
            patch(a => { a.error = undefined })
          }
        } catch (error) {
          if (!active()) return
          progress.failures += 1; progress.bytesPerSecond = 0
          progress.phase = error instanceof Error && /本地录像文件已丢失/.test(error.message) ? 'blocked' : 'retrying'
          progress.retryAt = Date.now() + Math.min(30000, 3000 * 2 ** Math.min(progress.failures - 1, 4))
          updateCountedSession(owner, session.id, s => { s.attempts.find(a => a.id === original.id)!.error = error instanceof Error ? error.message : '视频待补传' })
        }
      }
    }
  }
  const promise = run().finally(() => { inflight.delete(owner) })
  inflight.set(owner, promise); return promise
}
let retryTimer: ReturnType<typeof setInterval> | undefined
let retryEpoch = 0
let networkHandler: ((event: { isConnected: boolean }) => void) | undefined
export function stopCountedRetry() {
  retryEpoch += 1
  if (retryTimer) clearInterval(retryTimer)
  retryTimer = undefined
  if (networkHandler) { try { Taro.offNetworkStatusChange(networkHandler) } catch { /* optional */ } }
  networkHandler = undefined
  if (!inflight.size) uploadStates.clear()
}
export function startCountedRetry() {
  stopCountedRetry()
  if (isDemoSession() || !getPatientAppToken()) return
  const epoch = retryEpoch
  const token = getPatientAppToken()
  let owner: number | undefined
  let checking = false
  const tick = async () => {
    if (epoch !== retryEpoch || checking) return
    if (getPatientAppToken() !== token || isDemoSession()) { stopCountedRetry(); return }
    checking = true
    try {
      if (!Object.values(readQueue()).some(list => list.some(s => completedAttempts(s).some(a => !a.uploaded)))) return
      owner ??= (await fetchPatientHomeData()).project_patient_id
      if (epoch !== retryEpoch || getPatientAppToken() !== token) return
      await syncCountedQueue(owner, true)
    } catch { /* Keep the scheduler alive for the next network/identity attempt. */ }
    finally { checking = false }
  }
  networkHandler = event => {
    if (!event.isConnected) return
    for (const state of uploadStates.values()) if (state.phase === 'retrying') state.retryAt = 0
    void tick()
  }
  try { Taro.onNetworkStatusChange(networkHandler) } catch { /* optional */ }
  retryTimer = setInterval(() => { void tick() }, 1000)
  void tick()
}
