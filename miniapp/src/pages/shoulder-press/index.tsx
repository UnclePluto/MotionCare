import { Button, Camera, Text, Video, View } from '@tarojs/components'
import Taro, { useDidHide, useRouter } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import { request } from '../../api/client'
import type { CurrentPrescription } from '../../types/patientApp'
import {
  canCompleteShoulderPressTraining,
  canStartShoulderPressRecording,
  formatShoulderPressTimer,
  resolveShoulderPressAction,
  shoulderPressUploadCounters,
  shouldAutoFinishShoulderPressTraining,
  type ShoulderPressAction
} from './pageState'
import { ShoulderPressRecorder } from './recorder'
import {
  appendPendingSegment,
  buildShoulderPressUploadUrl,
  createPendingShoulderPressSession,
  loadPendingShoulderPressSession,
  savePendingShoulderPressSession,
  type PendingShoulderPressSegment,
  type PendingShoulderPressSession
} from './session'
import {
  createVideoSession,
  getVideoSessionStatus,
  uploadVideoSegment
} from './api'

type CameraContext = ReturnType<typeof Taro.createCameraContext>
type SessionUpdate = (session: PendingShoulderPressSession) => void

let backgroundUploadPromise: Promise<void> | null = null

function todayTrainingDate(): string {
  const date = new Date()
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0')
  ].join('-')
}

function expectedDurationSeconds(action: ShoulderPressAction): number {
  return Math.max(1, Math.round((action.duration_minutes || 1) * 60))
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

function persistSession(session: PendingShoulderPressSession, onSession?: SessionUpdate): PendingShoulderPressSession {
  savePendingShoulderPressSession(Taro, session)
  onSession?.(session)
  return session
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

async function ensureRemoteSession(
  session: PendingShoulderPressSession,
  onSession?: SessionUpdate
): Promise<PendingShoulderPressSession> {
  if (session.videoId) return session
  const created = await createVideoSession({
    actionId: session.actionId,
    clientSessionId: session.clientSessionId,
    trainingDate: session.trainingDate,
    expectedDurationSeconds: session.expectedDurationSeconds
  })
  return persistSession({
    ...mergeServerUploaded(session, created.uploaded_segments),
    videoId: created.video_id
  }, onSession)
}

async function uploadPendingSegments(onSession?: SessionUpdate): Promise<void> {
  let session = loadPendingShoulderPressSession(Taro)
  if (!session || session.finalized || session.segments.length === 0) return

  session = await ensureRemoteSession(session, onSession)
  const status = await getVideoSessionStatus(session.videoId)
  session = persistSession(mergeServerUploaded(session, status.uploaded_segments), onSession)

  for (;;) {
    session = loadPendingShoulderPressSession(Taro) ?? session
    if (session.finalized || !session.videoId) return

    const segment = session.segments.find((item) => item.uploadState !== 'uploaded')
    if (!segment) return

    session = persistSession(updateSegment(session, segment.index, {
      uploadState: 'uploading',
      sha256: undefined
    }), onSession)

    try {
      const uploaded = await uploadVideoSegment({
        videoId: session.videoId,
        index: segment.index,
        filePath: segment.savedFilePath,
        durationMs: segment.durationMs,
        sizeBytes: segment.sizeBytes
      })
      session = loadPendingShoulderPressSession(Taro) ?? session
      session = persistSession(updateSegment(session, uploaded.index, {
        uploadState: 'uploaded',
        sha256: uploaded.sha256
      }), onSession)
    } catch (error) {
      session = loadPendingShoulderPressSession(Taro) ?? session
      persistSession({
        ...updateSegment(session, segment.index, {
          uploadState: 'pending',
          sha256: undefined
        }),
        lastError: error instanceof Error ? error.message : '视频分段上传失败，请检查网络后重试'
      }, onSession)
      throw error
    }
  }
}

function uploadPendingSegmentsInBackground(onSession?: SessionUpdate): Promise<void> {
  if (backgroundUploadPromise) return backgroundUploadPromise

  let completedWithoutError = false
  backgroundUploadPromise = uploadPendingSegments(onSession)
    .then(() => {
      completedWithoutError = true
    })
    .catch(() => undefined)
    .finally(() => {
      backgroundUploadPromise = null
      const latest = loadPendingShoulderPressSession(Taro)
      const hasPending = latest?.segments.some((segment) => segment.uploadState !== 'uploaded') ?? false
      if (completedWithoutError && latest && !latest.finalized && hasPending) {
        void uploadPendingSegmentsInBackground(onSession)
      }
    })

  return backgroundUploadPromise
}

export default function ShoulderPressPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const [action, setAction] = useState<ShoulderPressAction | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [cameraReady, setCameraReady] = useState(false)
  const [recording, setRecording] = useState(false)
  const [paused, setPaused] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [session, setSession] = useState<PendingShoulderPressSession | null>(null)
  const [error, setError] = useState('')
  const [, setLiveTick] = useState(Date.now())
  const cameraContextRef = useRef<CameraContext | null>(null)
  const recorderRef = useRef<ShoulderPressRecorder | null>(null)
  const sessionRef = useRef<PendingShoulderPressSession | null>(null)
  const recordingRef = useRef(false)
  const pausedRef = useRef(false)
  const commandInFlightRef = useRef(false)
  const finishInFlightRef = useRef(false)
  const recordingStartedAtRef = useRef(0)
  const segmentSaveChainRef = useRef<Promise<void>>(Promise.resolve())

  function syncSession(nextSession: PendingShoulderPressSession) {
    sessionRef.current = nextSession
    setSession(nextSession)
    if (nextSession.lastError) setError(nextSession.lastError)
  }

  function saveCurrentSession(nextSession: PendingShoulderPressSession) {
    persistSession(nextSession, syncSession)
  }

  function currentElapsedMs(): number {
    const savedDuration = sessionRef.current?.actualDurationMs ?? session?.actualDurationMs ?? 0
    const liveDuration = recordingRef.current && recordingStartedAtRef.current > 0
      ? Math.max(0, Date.now() - recordingStartedAtRef.current)
      : 0
    return Math.min(savedDuration + liveDuration, 600_000)
  }

  async function persistRecordedSegment(tempFilePath: string): Promise<void> {
    const write = segmentSaveChainRef.current.then(async () => {
      const currentSession = sessionRef.current
      if (!currentSession) throw new Error('训练会话未准备好，请返回处方重新进入')

      const saved = await Taro.saveFile({ tempFilePath })
      const info = await Taro.getVideoInfo({ src: saved.savedFilePath })
      const nextSession = appendPendingSegment(currentSession, {
        savedFilePath: saved.savedFilePath,
        durationSeconds: info.duration,
        sizeKb: info.size
      })
      saveCurrentSession(nextSession)
      void uploadPendingSegmentsInBackground(syncSession)
    })

    segmentSaveChainRef.current = write.catch(() => undefined)
    try {
      await write
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : '录像分段保存失败，请重试')
      throw saveError
    }
  }

  function ensureRecorder(): ShoulderPressRecorder {
    if (recorderRef.current) return recorderRef.current
    const context = cameraContextRef.current ?? Taro.createCameraContext()
    cameraContextRef.current = context
    recorderRef.current = new ShoulderPressRecorder({
      camera: context,
      now: () => Date.now(),
      onSegment: (tempFilePath) => persistRecordedSegment(tempFilePath),
      onPause: () => {
        recordingRef.current = false
        pausedRef.current = true
        recordingStartedAtRef.current = 0
        setRecording(false)
        setPaused(true)
      }
    })
    return recorderRef.current
  }

  async function startTraining() {
    const canStart = canStartShoulderPressRecording({
      actionReady: action !== null && sessionRef.current !== null,
      cameraReady,
      busy: commandInFlightRef.current || finishInFlightRef.current || recordingRef.current
    })
    if (!canStart) {
      setError(action ? '摄像头尚未就绪，请开启权限后再继续训练' : '当前动作不可用，请返回处方重新进入')
      return
    }

    commandInFlightRef.current = true
    setProcessing(true)
    setError('')
    try {
      const recorder = ensureRecorder()
      await recorder.start()
      recordingRef.current = true
      pausedRef.current = false
      recordingStartedAtRef.current = Date.now()
      setRecording(true)
      setPaused(false)
      try {
        Taro.createVideoContext('shoulder-press-example-video').play()
      } catch {
        // 示例视频自动播放失败不影响患者开始录像。
      }
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : '摄像头录像启动失败，请检查权限后重试')
    } finally {
      commandInFlightRef.current = false
      setProcessing(false)
    }
  }

  async function pauseTraining() {
    if (!recorderRef.current || !recordingRef.current) return
    try {
      await recorderRef.current.pause()
    } catch (pauseError) {
      setError(pauseError instanceof Error ? pauseError.message : '暂停录像失败，请稍后重试')
    } finally {
      recordingRef.current = false
      pausedRef.current = true
      recordingStartedAtRef.current = 0
      setRecording(false)
      setPaused(true)
    }
  }

  async function finishTraining(force = false) {
    if (finishInFlightRef.current) return
    const elapsedMs = currentElapsedMs()
    const expectedSeconds = sessionRef.current?.expectedDurationSeconds ?? session?.expectedDurationSeconds ?? 1
    if (!force && !canCompleteShoulderPressTraining({
      actualDurationMs: elapsedMs,
      expectedDurationSeconds: expectedSeconds
    })) {
      setError('达到本次处方训练时长后才能完成。')
      return
    }

    finishInFlightRef.current = true
    commandInFlightRef.current = true
    setProcessing(true)
    setError('')
    try {
      if (recorderRef.current) {
        await recorderRef.current.finish()
      }
      await segmentSaveChainRef.current
      const currentSession = sessionRef.current
      if (!currentSession || currentSession.segments.length === 0) {
        throw new Error('还没有可上传的训练片段，请先开始训练')
      }
      recordingRef.current = false
      pausedRef.current = false
      setRecording(false)
      setPaused(false)
      await Taro.reLaunch({ url: buildShoulderPressUploadUrl() })
    } catch (finishError) {
      setError(finishError instanceof Error ? finishError.message : '训练完成失败，请重试')
    } finally {
      finishInFlightRef.current = false
      commandInFlightRef.current = false
      setProcessing(false)
    }
  }

  useEffect(() => {
    const pending = loadPendingShoulderPressSession(Taro)
    if (pending && !pending.finalized) {
      Taro.reLaunch({ url: buildShoulderPressUploadUrl() })
      return
    }

    if (!Number.isInteger(actionId) || actionId <= 0) {
      setError('训练动作无效，请返回当前处方重新进入')
      setLoaded(true)
      return
    }

    request<CurrentPrescription>('/patient-app/current-prescription/')
      .then((prescription) => {
        const currentAction = resolveShoulderPressAction(prescription, actionId)
        setAction(currentAction)
        if (!currentAction) {
          setError('动作已失效或处方已更新，请返回当前处方重新进入')
          return
        }
        const nextSession = createPendingShoulderPressSession({
          actionId,
          expectedDurationSeconds: expectedDurationSeconds(currentAction),
          trainingDate: todayTrainingDate()
        })
        sessionRef.current = nextSession
        setSession(nextSession)
      })
      .catch((loadError) => {
        setError(loadError instanceof Error ? loadError.message : '当前动作加载失败，请稍后重试')
      })
      .finally(() => setLoaded(true))
  }, [actionId])

  useEffect(() => {
    if (!recording) return undefined
    const timer = setInterval(() => {
      const elapsedMs = currentElapsedMs()
      setLiveTick(Date.now())
      if (shouldAutoFinishShoulderPressTraining(elapsedMs)) {
        void finishTraining(true)
      }
    }, 1000)
    return () => clearInterval(timer)
  }, [recording])

  useDidHide(() => {
    void pauseTraining()
  })

  const elapsedMs = currentElapsedMs()
  const counters = shoulderPressUploadCounters(session?.segments ?? [])
  const canFinish = canCompleteShoulderPressTraining({
    actualDurationMs: elapsedMs,
    expectedDurationSeconds: session?.expectedDurationSeconds ?? 1
  })
  const timerText = formatShoulderPressTimer(elapsedMs)
  const remainingSeconds = Math.max(0, Math.ceil(((session?.expectedDurationSeconds ?? 1) * 1000 - elapsedMs) / 1000))
  const canStart = canStartShoulderPressRecording({
    actionReady: action !== null && session !== null,
    cameraReady,
    busy: processing || recording
  })
  const statusText = recording
    ? '正在录像，保持动作完整入镜。'
    : paused || pausedRef.current
      ? '训练已暂停，点击继续训练后再录像。'
      : '准备好后点击开始训练。'

  return (
    <View className='page shoulder-press-page'>
      <View className='page-hero shoulder-press-hero'>
        <Text className='eyebrow'>抗阻训练</Text>
        <Text className='title'>{action?.action_name ?? '肩部推举'}</Text>
        <Text className='muted'>前置摄像头会记录动作，请跟随示例缓慢完成。</Text>
      </View>

      <View className='training-stage'>
        <View className='training-media-slot'>
          <Text className='training-media-label'>我的画面</Text>
          <View className='training-media-frame camera-frame'>
            <Camera
              className='camera-preview'
              devicePosition='front'
              flash='off'
              mode='normal'
              onInitDone={() => {
                setCameraReady(true)
              }}
              onError={() => {
                setCameraReady(false)
                setError('请开启摄像头权限，摄像头可用后才能开始录像')
              }}
            />
          </View>
        </View>
        <View className='training-media-slot'>
          <Text className='training-media-label'>示例动作</Text>
          <View className='training-media-frame example-frame'>
            {action?.video_url ? (
              <Video
                id='shoulder-press-example-video'
                className='example-video'
                src={action.video_url}
                title={action.action_name}
                controls
                loop
                objectFit='contain'
                showFullscreenBtn={false}
                showCenterPlayBtn
                enableProgressGesture
              />
            ) : (
              <View className='example-fallback'>
                <Text className='label'>动作说明</Text>
                <Text className='paragraph'>
                  {action?.action_instruction || '医生暂未配置示例视频，请按动作说明缓慢完成肩部推举。'}
                </Text>
              </View>
            )}
          </View>
        </View>
      </View>

      <View className='recording-dashboard'>
        <View className='recording-metric'>
          <Text className='label'>录像计时</Text>
          <Text className='recording-timer'>{timerText}</Text>
        </View>
        <View className='recording-metric'>
          <Text className='label'>分段上传</Text>
          <Text className='recording-count'>{counters.uploaded}/{counters.total}</Text>
        </View>
        <View className='recording-metric recording-metric-wide'>
          <Text className='label'>当前状态</Text>
          <Text className='recording-state-text'>{statusText}</Text>
        </View>
      </View>

      {!loaded ? <Text className='muted loading-text'>正在加载当前动作</Text> : null}
      {!canFinish && session?.segments.length ? (
        <Text className='recording-status'>还需约 {remainingSeconds} 秒，可完成本次训练。</Text>
      ) : null}
      {error ? <Text className='error'>{error}</Text> : null}

      {!action && loaded ? (
        <Button
          className='secondary-button full-button'
          onClick={() => Taro.reLaunch({ url: '/pages/prescription/index' })}
        >
          返回当前处方
        </Button>
      ) : recording ? (
        <Button
          className='primary-button full-button'
          loading={processing}
          disabled={processing || !canFinish}
          onClick={() => void finishTraining()}
        >
          完成训练
        </Button>
      ) : paused ? (
        <View className='button-row shoulder-press-action-row'>
          <Button
            className='primary-button'
            loading={processing}
            disabled={!canStart}
            onClick={() => void startTraining()}
          >
            继续训练
          </Button>
          <Button
            className='secondary-button'
            loading={processing}
            disabled={processing || !canFinish}
            onClick={() => void finishTraining()}
          >
            完成训练
          </Button>
        </View>
      ) : (
        <Button
          className='primary-button full-button'
          loading={processing}
          disabled={!canStart}
          onClick={() => void startTraining()}
        >
          开始训练
        </Button>
      )}
    </View>
  )
}
