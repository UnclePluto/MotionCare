import { Button, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useRef, useState } from 'react'

import { saveTemporaryMotionTrainingSegmentForRetry } from '../../features/motion-training/localFile'
import {
  isServerRetryableFinalizeStatus,
  isServerSafeFinalizeStatus,
  loadOwnedPendingMotionTrainingSession,
  saveOwnedPendingMotionTrainingSession,
  motionTrainingUploadCounters,
  type TrainingVideoStatus
} from '../../features/motion-training/pageState'
import {
  clearPendingMotionTrainingSession,
  isCompressedMotionTrainingSegment,
  loadPendingMotionTrainingSession,
  promoteLegacyMotionTrainingSegment,
  requireMotionTrainingStartedAt,
  type CompressedMotionTrainingSegment,
  type PendingMotionTrainingSegment,
  type PendingMotionTrainingSession
} from '../../features/motion-training/session'
import {
  createVideoSession,
  finalizeVideoSession,
  getVideoSessionStatus,
  uploadVideoSegment,
  type VideoSessionStatus
} from '../../features/motion-training/api'

type UploadPhase = 'preparing' | 'session' | 'status' | 'segments' | 'finalize' | 'done'
const ABANDONED_MOTION_TRAINING_FILES_KEY = 'motioncare.motionTraining.abandonedFiles.v1'

const PHASE_LABELS: Record<UploadPhase, string> = {
  preparing: '准备训练分段',
  session: '建立上传会话',
  status: '确认已上传片段',
  segments: '上传训练分段',
  finalize: '提交处理',
  done: '已提交'
}

function mediaErrorDetail(error: unknown): string {
  if (error instanceof Error) return error.message.trim()
  if (error && typeof error === 'object') {
    const errMsg = (error as { errMsg?: unknown }).errMsg
    if (typeof errMsg === 'string') return errMsg.trim()
  }
  return ''
}

function updateSegment(
  session: PendingMotionTrainingSession,
  index: number,
  update: Partial<CompressedMotionTrainingSegment>
): PendingMotionTrainingSession {
  return {
    ...session,
    segments: session.segments.map((segment) => (
      segment.index === index && isCompressedMotionTrainingSegment(segment)
        ? { ...segment, ...update }
        : segment
    ))
  }
}

function mergeServerUploaded(
  session: PendingMotionTrainingSession,
  uploadedSegments: number[] | undefined
): PendingMotionTrainingSession {
  const uploaded = new Set((uploadedSegments ?? []).filter((index) => (
    Number.isInteger(index) && index >= 0 && index < session.segments.length
  )))
  return {
    ...session,
    segments: session.segments.map((segment) => {
      if (!isCompressedMotionTrainingSegment(segment)) return segment
      if (uploaded.has(segment.index)) return { ...segment, uploadState: 'uploaded' }
      if (segment.uploadState === 'uploading') return { ...segment, uploadState: 'pending', sha256: undefined }
      return segment
    })
  }
}

function statusMessage(status: TrainingVideoStatus | string): string {
  if (status === 'failed') return '处理失败，本地视频仍保留。请重试上传或重新训练。'
  if (status === 'expired') return '上传会话已过期，本地视频仍保留。请重新训练。'
  return '上传失败，本地视频仍保留。请检查网络后重试。'
}

function deleteSavedFile(path: string): Promise<boolean> {
  return new Promise((resolve) => {
    try {
      Taro.getFileSystemManager().unlink({
        filePath: path,
        success: () => resolve(true),
        fail: () => resolve(false)
      })
    } catch {
      resolve(false)
    }
  })
}

async function cleanupAfterServerReceipt(session: PendingMotionTrainingSession): Promise<void> {
  const failedPaths: string[] = []
  try {
    for (const segment of session.segments) {
      const filePath = isCompressedMotionTrainingSegment(segment)
        ? segment.savedFilePath
        : segment.rawSavedFilePath
      if (!await deleteSavedFile(filePath)) {
        failedPaths.push(filePath)
      }
    }
    if (failedPaths.length > 0) {
      Taro.setStorageSync(ABANDONED_MOTION_TRAINING_FILES_KEY, {
        paths: failedPaths,
        recordedAt: Date.now()
      })
    } else {
      Taro.removeStorageSync(ABANDONED_MOTION_TRAINING_FILES_KEY)
    }
  } finally {
    clearPendingMotionTrainingSession(Taro)
  }
}

export default function MotionTrainingUploadPage() {
  const [pending, setPending] = useState<PendingMotionTrainingSession | null>(() => (
    loadPendingMotionTrainingSession(Taro)
  ))
  const [phase, setPhase] = useState<UploadPhase>('session')
  const [activeIndex, setActiveIndex] = useState<number | null>(null)
  const [segmentProgress, setSegmentProgress] = useState(0)
  const [running, setRunning] = useState(false)
  const [missing, setMissing] = useState(pending === null)
  const [error, setError] = useState('')
  const runningRef = useRef(false)

  function persist(session: PendingMotionTrainingSession): PendingMotionTrainingSession | null {
    const saved = saveOwnedPendingMotionTrainingSession(Taro, session)
    if (!saved) return null
    setPending(saved)
    return saved
  }

  async function leaveAfterSafeReceipt(session: PendingMotionTrainingSession) {
    setPhase('done')
    await cleanupAfterServerReceipt(session)
    await Taro.reLaunch({ url: '/pages/prescription/index' })
  }

  async function ensureVideoSession(session: PendingMotionTrainingSession): Promise<PendingMotionTrainingSession | null> {
    setPhase('session')
    if (session.videoId) return session
    const trainingStartedAt = requireMotionTrainingStartedAt(session)
    const created = await createVideoSession({
      actionId: session.actionId,
      clientSessionId: session.clientSessionId,
      trainingDate: session.trainingDate,
      expectedDurationSeconds: session.expectedDurationSeconds,
      trainingStartedAt
    })
    const latest = loadOwnedPendingMotionTrainingSession(Taro, session.clientSessionId)
    if (!latest) return null
    const nextSession = persist({
      ...mergeServerUploaded(latest, created.uploaded_segments),
      videoId: created.video_id
    })
    if (!nextSession) return null
    if (isServerRetryableFinalizeStatus(created.status)) {
      throw new Error(statusMessage(created.status))
    }
    if (isServerSafeFinalizeStatus(created.status)) {
      await leaveAfterSafeReceipt({ ...nextSession, finalized: true })
      return null
    }
    return nextSession
  }

  async function preparePendingSegments(
    initialSession: PendingMotionTrainingSession
  ): Promise<PendingMotionTrainingSession | null> {
    setPhase('preparing')
    const clientSessionId = initialSession.clientSessionId
    let current = initialSession

    for (;;) {
      const latest = loadOwnedPendingMotionTrainingSession(Taro, clientSessionId)
      if (!latest) return null
      current = latest
      const segment = current.segments.find((item) => !isCompressedMotionTrainingSegment(item))
      if (!segment || isCompressedMotionTrainingSegment(segment)) return current
      setActiveIndex(segment.index)
      setSegmentProgress(0)

      try {
        const fileInfo = await Taro.getFileInfo({ filePath: segment.rawSavedFilePath })
        const sizeBytes = Number(fileInfo.size)
        if (!Number.isInteger(sizeBytes) || sizeBytes <= 0) {
          throw new Error('录像文件大小无效')
        }
        const beforePersist = loadOwnedPendingMotionTrainingSession(Taro, clientSessionId)
        if (!beforePersist) return null
        current = persist(promoteLegacyMotionTrainingSegment(
          beforePersist,
          segment.index,
          {
            savedFilePath: segment.rawSavedFilePath,
            durationMs: segment.durationMs,
            sizeBytes,
            localFileState: segment.rawSavedFilePath.includes('wxfile://temp')
              ? 'temporary'
              : 'saved'
          }
        ))
        if (!current) return null
        setSegmentProgress(100)
      } catch (preparationError) {
        const detail = mediaErrorDetail(preparationError)
        throw new Error(detail
          ? `录像文件已失效，请重新训练：${detail}`
          : '录像文件已失效，请重新训练')
      }
    }
  }

  async function mergeRemoteStatus(session: PendingMotionTrainingSession): Promise<PendingMotionTrainingSession | null> {
    if (!session.videoId) return session
    setPhase('status')
    const status = await getVideoSessionStatus(session.videoId)
    const latest = loadOwnedPendingMotionTrainingSession(Taro, session.clientSessionId)
    if (!latest) return null
    const nextSession = persist(mergeServerUploaded({
      ...latest,
      videoId: session.videoId
    }, status.uploaded_segments))
    if (!nextSession) return null
    if (isServerSafeFinalizeStatus(status.status)) {
      await leaveAfterSafeReceipt({ ...nextSession, finalized: true })
      return null
    }
    if (isServerRetryableFinalizeStatus(status.status)) {
      throw new Error(statusMessage(status.status))
    }
    return nextSession
  }

  async function uploadSegments(session: PendingMotionTrainingSession): Promise<PendingMotionTrainingSession | null> {
    if (!session.videoId) return session
    setPhase('segments')
    const clientSessionId = session.clientSessionId
    let current = session

    for (;;) {
      const latest = loadOwnedPendingMotionTrainingSession(Taro, clientSessionId)
      if (!latest) return null
      current = latest
      if (!current.videoId) return null
      const segment = current.segments.find((item) => (
        isCompressedMotionTrainingSegment(item) && item.uploadState !== 'uploaded'
      ))
      if (!segment) break
      if (!isCompressedMotionTrainingSegment(segment)) {
        throw new Error('录像分段尚未压缩，请重试')
      }
      setActiveIndex(segment.index)
      setSegmentProgress(0)

      current = persist(updateSegment(current, segment.index, {
        uploadState: 'uploading',
        sha256: undefined
      }))
      if (!current || !current.videoId) return null

      try {
        const uploaded = await uploadVideoSegment({
          videoId: current.videoId,
          index: segment.index,
          filePath: segment.savedFilePath,
          durationMs: segment.durationMs,
          sizeBytes: segment.sizeBytes,
          onProgress: (progress) => setSegmentProgress(progress)
        })
        current = loadOwnedPendingMotionTrainingSession(Taro, clientSessionId)
        if (!current) return null
        current = persist(updateSegment(current, uploaded.index, {
          uploadState: 'uploaded',
          sha256: uploaded.sha256
        }))
        if (!current) return null
        setSegmentProgress(100)
      } catch (uploadError) {
        current = loadOwnedPendingMotionTrainingSession(Taro, clientSessionId)
        if (!current) return null
        const retained = await saveTemporaryMotionTrainingSegmentForRetry({
          filePath: segment.savedFilePath,
          localFileState: segment.localFileState ?? 'saved'
        }, (options) => Taro.saveFile(options))
        current = loadOwnedPendingMotionTrainingSession(Taro, clientSessionId)
        if (!current) return null
        persist({
          ...updateSegment(current, segment.index, {
            savedFilePath: retained.filePath,
            localFileState: retained.localFileState,
            uploadState: 'pending',
            sha256: undefined
          }),
          lastError: uploadError instanceof Error ? uploadError.message : '视频分段上传失败，请检查网络后重试'
        })
        throw uploadError
      }
    }

    setActiveIndex(null)
    return current
  }

  async function finalizeSession(session: PendingMotionTrainingSession): Promise<VideoSessionStatus> {
    if (!session.videoId) throw new Error('上传会话缺失，请重试')
    setPhase('finalize')
    return finalizeVideoSession({
      videoId: session.videoId,
      segmentCount: session.segments.length,
      actualDurationSeconds: Math.ceil(session.actualDurationMs / 1000),
      note: '',
      trainingEndedAt: session.trainingEndedAt
    })
  }

  async function upload() {
    if (runningRef.current) return
    runningRef.current = true
    setRunning(true)
    setMissing(false)
    setError('')

    const currentPending = loadPendingMotionTrainingSession(Taro)
    if (!currentPending) {
      setPending(null)
      setMissing(true)
      runningRef.current = false
      setRunning(false)
      return
    }
    setPending(currentPending)

    try {
      if (currentPending.segments.length === 0) {
        throw new Error('没有可上传的训练片段，请重新训练')
      }
      let session = await preparePendingSegments(currentPending)
      if (!session) return
      session = await ensureVideoSession(session)
      if (!session) return
      session = await mergeRemoteStatus(session)
      if (!session) return
      session = await uploadSegments(session)
      if (!session) return
      const finalized = await finalizeSession(session)

      if (isServerSafeFinalizeStatus(finalized.status)) {
        await leaveAfterSafeReceipt({ ...session, finalized: true })
        return
      }

      if (isServerRetryableFinalizeStatus(finalized.status)) {
        persist({ ...session, lastError: statusMessage(finalized.status) })
        setError(statusMessage(finalized.status))
        return
      }

      throw new Error('服务端仍在接收视频，请稍后重试。')
    } catch (uploadError) {
      setPending(loadPendingMotionTrainingSession(Taro))
      setError(uploadError instanceof Error ? uploadError.message : '上传失败，请检查网络后重试')
    } finally {
      runningRef.current = false
      setRunning(false)
    }
  }

  async function restartTraining() {
    const current = loadPendingMotionTrainingSession(Taro)
    if (!current) return
    await cleanupAfterServerReceipt(current)
    await Taro.reLaunch({ url: `/pages/motion-training/index?actionId=${encodeURIComponent(String(current.actionId))}` })
  }

  useDidShow(() => {
    void upload()
  })

  const counters = motionTrainingUploadCounters(pending?.segments ?? [])
  const phaseLabel = PHASE_LABELS[phase]

  if (missing) {
    return (
      <View className='page motion-training-upload-page upload-invalid-page'>
        <View className='page-hero'>
          <Text className='eyebrow'>录像信息失效</Text>
          <Text className='title'>无法继续上传</Text>
          <Text className='muted'>本地录像信息缺失，请返回当前运动计划重新开始训练。</Text>
        </View>
        <Button
          className='secondary-button full-button'
          onClick={() => Taro.reLaunch({ url: '/pages/prescription/index' })}
        >
          返回当前运动计划
        </Button>
      </View>
    )
  }

  return (
    <View className='page motion-training-upload-page'>
      <View className='page-hero upload-hero'>
        <Text className='eyebrow'>训练上传</Text>
        <Text className='title'>请保持小程序打开</Text>
        <Text className='muted'>分段视频提交完成后，将自动返回当前运动计划。</Text>
      </View>

      <View className='upload-progress-panel segment-upload-panel'>
        <View className='upload-stage upload-stage-active'>
          <Text className='upload-stage-label'>{phaseLabel}</Text>
          <Text className='upload-stage-status'>{running ? '进行中' : '等待重试'}</Text>
        </View>
        <View className='upload-meter'>
          <View className='row upload-counter-row'>
            <Text className='label'>分段上传</Text>
            <Text className='value'>{counters.uploaded}/{counters.total}</Text>
          </View>
          <View className='progress-track'>
            <View className='progress-fill' style={{ width: `${counters.percent}%` }} />
          </View>
        </View>
        <View className='upload-meter'>
          <View className='row upload-counter-row'>
            <Text className='label'>当前分段</Text>
            <Text className='value'>{activeIndex === null ? '待提交' : `${activeIndex + 1}`}</Text>
          </View>
          <View className='progress-track'>
            <View className='progress-fill' style={{ width: `${segmentProgress}%` }} />
          </View>
        </View>
      </View>

      <Text className='upload-lock-note'>完成前请不要退出此页。</Text>
      {error ? <Text className='error'>{error}</Text> : null}
      {error ? (
        <View className='button-row motion-training-action-row'>
          <Button
            className='primary-button'
            loading={running}
            disabled={running}
            onClick={() => void upload()}
          >
            重试上传
          </Button>
          <Button
            className='secondary-button'
            disabled={running}
            onClick={() => void restartTraining()}
          >
            重新训练
          </Button>
        </View>
      ) : (
        <Text className='muted upload-running-text'>正在自动处理，请稍候。</Text>
      )}
    </View>
  )
}
