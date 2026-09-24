// Compatibility for queues created before whole-file recording. New groups never use this path.
import Taro from '@tarojs/taro'
import { createVideoSession, finalizeVideoSession, getVideoSessionStatus, uploadVideoSegment } from './api'
import { createClientSessionId } from './session'
import type { CountedAttempt, CountedSession, CountedUploadState } from './countedSession'
export async function uploadLegacyCountedAttempt(session: CountedSession, original: CountedAttempt, progress: CountedUploadState,
  active: () => boolean, save: (change: (a: CountedAttempt) => void) => void) {
  let attempt = original
  const segments = attempt.segments ?? []
  const patch = (change: (a: CountedAttempt) => void) => { save(change); attempt = { ...attempt }; change(attempt) }
  let status = attempt.videoId ? await getVideoSessionStatus(attempt.videoId) : undefined
  if (!active()) return undefined
  if (status && ['expired', 'failed'].includes(status.status)) { patch(a => { a.videoId = undefined; a.uploadId = createClientSessionId() }); status = undefined }
  if (!status) {
    status = await createVideoSession({ actionId: session.actionId, clientSessionId: attempt.uploadId,
      trainingDate: session.trainingDate, trainingStartedAt: attempt.startedAt, expectedDurationSeconds: 1800,
      motionAttemptId: attempt.id })
    if (!active()) return undefined
    patch(a => { a.videoId = status!.video_id })
  }
  const totalBytes = segments.reduce((sum, segment) => sum + segment.sizeBytes, 0)
  let sentBytes = segments.reduce((sum, segment, index) => sum + (status!.uploaded_segments?.includes(index) ? segment.sizeBytes : 0), 0)
  progress.percent = totalBytes ? Math.min(100, Math.floor(sentBytes / totalBytes * 100)) : 0
  if (status.status !== 'attached' && !['queued', 'assembling', 'uploading_qiniu'].includes(status.status)) {
    for (let index = 0; index < segments.length; index++) {
      if (!active()) return undefined
      if (status.uploaded_segments?.includes(index)) continue
      const segment = segments[index]
      try { await Taro.getFileInfo({ filePath: segment.path }) } catch { throw new Error('本地录像文件已丢失，无法完成上传。请联系指导老师。') }
      if (!active()) return undefined
      const segmentStartedAt = Date.now()
      await uploadVideoSegment({ videoId: status.video_id, clientSessionId: attempt.uploadId, index,
        filePath: segment.path, durationMs: segment.durationMs, sizeBytes: segment.sizeBytes,
        onProgress: (percent, bytesSent) => {
          if (!active()) return undefined
          const bytes = Math.min(segment.sizeBytes, Math.max(0, bytesSent ?? segment.sizeBytes * percent / 100))
          progress.percent = totalBytes ? Math.min(100, Math.floor((sentBytes + bytes) / totalBytes * 100)) : 0
          progress.updatedAt = Date.now()
          progress.bytesPerSecond = bytes * 1000 / Math.max(1, Date.now() - segmentStartedAt)
        } })
      sentBytes += segment.sizeBytes
      progress.percent = totalBytes ? Math.min(100, Math.floor(sentBytes / totalBytes * 100)) : 0
    }
    if (!active()) return undefined
    progress.phase = 'confirming'; progress.percent = 100; progress.bytesPerSecond = 0
    status = await finalizeVideoSession({ videoId: status.video_id, clientSessionId: attempt.uploadId,
      segmentCount: segments.length, actualDurationSeconds: Math.max(1, Math.round(segments.reduce((sum, p) => sum + p.durationMs, 0) / 1000)),
      trainingEndedAt: attempt.endedAt, note: '' })
  }
  return status
}
