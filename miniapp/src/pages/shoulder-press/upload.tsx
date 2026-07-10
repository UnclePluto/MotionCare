import { Button, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useRef, useState } from 'react'

import {
  isServerRetryableFinalizeStatus,
  isServerSafeFinalizeStatus,
  shoulderPressUploadCounters,
  type TrainingVideoStatus
} from './pageState'
import {
  clearPendingShoulderPressSession,
  loadPendingShoulderPressSession,
  savePendingShoulderPressSession,
  type PendingShoulderPressSegment,
  type PendingShoulderPressSession
} from './session'
import {
  createVideoSession,
  finalizeVideoSession,
  getVideoSessionStatus,
  uploadVideoSegment,
  type VideoSessionStatus
} from './api'

type UploadPhase = 'session' | 'status' | 'segments' | 'finalize' | 'done'

const PHASE_LABELS: Record<UploadPhase, string> = {
  session: '建立上传会话',
  status: '确认已上传片段',
  segments: '上传训练分段',
  finalize: '提交处理',
  done: '已提交'
}

function updateSegment(
  session: PendingShoulderPressSession,
  index: number,
  update: Partial<PendingShoulderPressSegment>
): PendingShoulderPressSession {
  return {
    ...session,
    segments: session.segments.map((segment) => (
      segment.index === index ? { ...segment, ...update } : segment
    ))
  }
}

function mergeServerUploaded(
  session: PendingShoulderPressSession,
  uploadedSegments: number[] | undefined
): PendingShoulderPressSession {
  const uploaded = new Set((uploadedSegments ?? []).filter((index) => (
    Number.isInteger(index) && index >= 0 && index < session.segments.length
  )))
  return {
    ...session,
    segments: session.segments.map((segment) => {
      if (uploaded.has(segment.index)) return { ...segment, uploadState: 'uploaded' }
      if (segment.uploadState === 'uploading') return { ...segment, uploadState: 'pending', sha256: undefined }
      return segment
    })
  }
}

function statusMessage(status: TrainingVideoStatus | string): string {
  if (status === 'failed') return '服务端处理失败，请重试上传或重新训练。'
  if (status === 'expired') return '本次上传会话已过期，请重新训练。'
  return '上传失败，请检查网络后重试。'
}

function deleteSavedFile(path: string): Promise<void> {
  return new Promise((resolve) => {
    try {
      Taro.getFileSystemManager().unlink({
        filePath: path,
        success: () => resolve(),
        fail: () => resolve()
      })
    } catch {
      resolve()
    }
  })
}

async function cleanupAfterServerReceipt(session: PendingShoulderPressSession): Promise<void> {
  try {
    for (const segment of session.segments) {
      await deleteSavedFile(segment.savedFilePath)
    }
  } finally {
    clearPendingShoulderPressSession(Taro)
  }
}

export default function ShoulderPressUploadPage() {
  const [pending, setPending] = useState<PendingShoulderPressSession | null>(() => (
    loadPendingShoulderPressSession(Taro)
  ))
  const [phase, setPhase] = useState<UploadPhase>('session')
  const [activeIndex, setActiveIndex] = useState<number | null>(null)
  const [segmentProgress, setSegmentProgress] = useState(0)
  const [running, setRunning] = useState(false)
  const [missing, setMissing] = useState(pending === null)
  const [error, setError] = useState('')
  const runningRef = useRef(false)

  function persist(session: PendingShoulderPressSession): PendingShoulderPressSession {
    savePendingShoulderPressSession(Taro, session)
    setPending(session)
    return session
  }

  async function leaveAfterSafeReceipt(session: PendingShoulderPressSession) {
    setPhase('done')
    await cleanupAfterServerReceipt(session)
    await Taro.reLaunch({ url: '/pages/prescription/index' })
  }

  async function ensureVideoSession(session: PendingShoulderPressSession): Promise<PendingShoulderPressSession | null> {
    setPhase('session')
    if (session.videoId) return session
    const created = await createVideoSession({
      actionId: session.actionId,
      clientSessionId: session.clientSessionId,
      trainingDate: session.trainingDate,
      expectedDurationSeconds: session.expectedDurationSeconds
    })
    const nextSession = persist({
      ...mergeServerUploaded(session, created.uploaded_segments),
      videoId: created.video_id
    })
    if (isServerRetryableFinalizeStatus(created.status)) {
      throw new Error(statusMessage(created.status))
    }
    if (isServerSafeFinalizeStatus(created.status)) {
      await leaveAfterSafeReceipt({ ...nextSession, finalized: true })
      return null
    }
    return nextSession
  }

  async function mergeRemoteStatus(session: PendingShoulderPressSession): Promise<PendingShoulderPressSession | null> {
    if (!session.videoId) return session
    setPhase('status')
    const status = await getVideoSessionStatus(session.videoId)
    const nextSession = persist(mergeServerUploaded(session, status.uploaded_segments))
    if (isServerSafeFinalizeStatus(status.status)) {
      await leaveAfterSafeReceipt({ ...nextSession, finalized: true })
      return null
    }
    if (isServerRetryableFinalizeStatus(status.status)) {
      throw new Error(statusMessage(status.status))
    }
    return nextSession
  }

  async function uploadSegments(session: PendingShoulderPressSession): Promise<PendingShoulderPressSession> {
    if (!session.videoId) return session
    setPhase('segments')
    let current = session

    for (const segment of current.segments) {
      if (segment.uploadState === 'uploaded') continue
      setActiveIndex(segment.index)
      setSegmentProgress(0)

      current = persist(updateSegment(current, segment.index, {
        uploadState: 'uploading',
        sha256: undefined
      }))

      try {
        const uploaded = await uploadVideoSegment({
          videoId: current.videoId,
          index: segment.index,
          filePath: segment.savedFilePath,
          durationMs: segment.durationMs,
          sizeBytes: segment.sizeBytes,
          onProgress: (progress) => setSegmentProgress(progress)
        })
        current = loadPendingShoulderPressSession(Taro) ?? current
        current = persist(updateSegment(current, uploaded.index, {
          uploadState: 'uploaded',
          sha256: uploaded.sha256
        }))
        setSegmentProgress(100)
      } catch (uploadError) {
        current = loadPendingShoulderPressSession(Taro) ?? current
        persist({
          ...updateSegment(current, segment.index, {
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

  async function finalizeSession(session: PendingShoulderPressSession): Promise<VideoSessionStatus> {
    if (!session.videoId) throw new Error('上传会话缺失，请重试')
    setPhase('finalize')
    return finalizeVideoSession({
      videoId: session.videoId,
      segmentCount: session.segments.length,
      actualDurationSeconds: Math.ceil(session.actualDurationMs / 1000),
      note: ''
    })
  }

  async function upload() {
    if (runningRef.current) return
    runningRef.current = true
    setRunning(true)
    setMissing(false)
    setError('')

    const currentPending = loadPendingShoulderPressSession(Taro)
    if (!currentPending) {
      setPending(null)
      setMissing(true)
      runningRef.current = false
      setRunning(false)
      return
    }
    setPending(currentPending)

    try {
      let session = await ensureVideoSession(currentPending)
      if (!session) return
      session = await mergeRemoteStatus(session)
      if (!session) return
      session = await uploadSegments(session)
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
      setPending(loadPendingShoulderPressSession(Taro))
      setError(uploadError instanceof Error ? uploadError.message : '上传失败，请检查网络后重试')
    } finally {
      runningRef.current = false
      setRunning(false)
    }
  }

  function restartTraining() {
    const current = loadPendingShoulderPressSession(Taro)
    if (!current) return
    clearPendingShoulderPressSession(Taro)
    Taro.reLaunch({ url: `/pages/shoulder-press/index?actionId=${encodeURIComponent(String(current.actionId))}` })
  }

  useDidShow(() => {
    void upload()
  })

  const counters = shoulderPressUploadCounters(pending?.segments ?? [])
  const phaseLabel = PHASE_LABELS[phase]

  if (missing) {
    return (
      <View className='page shoulder-press-upload-page upload-invalid-page'>
        <View className='page-hero'>
          <Text className='eyebrow'>录像信息失效</Text>
          <Text className='title'>无法继续上传</Text>
          <Text className='muted'>本地录像信息缺失，请返回当前处方重新开始训练。</Text>
        </View>
        <Button
          className='secondary-button full-button'
          onClick={() => Taro.reLaunch({ url: '/pages/prescription/index' })}
        >
          返回当前处方
        </Button>
      </View>
    )
  }

  return (
    <View className='page shoulder-press-upload-page'>
      <View className='page-hero upload-hero'>
        <Text className='eyebrow'>训练上传</Text>
        <Text className='title'>请保持小程序打开</Text>
        <Text className='muted'>分段视频提交完成后，将自动返回当前处方。</Text>
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
        <View className='button-row shoulder-press-action-row'>
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
            onClick={restartTraining}
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
