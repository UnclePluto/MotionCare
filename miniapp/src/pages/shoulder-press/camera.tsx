import { Button, Camera, Text, View } from '@tarojs/components'
import Taro, { useDidHide, useRouter } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import { request } from '../../api/client'
import { containsSensitiveCredentialText } from '../../api/safeError'
import type { CurrentPrescription } from '../../types/patientApp'
import { saveTemporaryShoulderPressSegmentForRetry } from './localFile'
import {
  canCompleteShoulderPressTraining,
  canStartShoulderPressRecording,
  computeShoulderPressEffectiveDuration,
  formatShoulderPressTimer,
  loadOwnedPendingShoulderPressSession,
  registerShoulderPressBackgroundUpload,
  reLaunchPendingShoulderPressUploadIfNeeded,
  resolveShoulderPressAction,
  saveOwnedPendingShoulderPressSession,
  shoulderPressUploadCounters,
  SHOULDER_PRESS_RECORDING_STOP_MS,
  shouldAutoFinishShoulderPressTraining,
  waitForShoulderPressBackgroundUploadSettled,
  type ShoulderPressAction
} from './pageState'
import { ShoulderPressRecorder } from './recorder'
import {
  appendUploadableShoulderPressSegment,
  buildShoulderPressSessionUrl,
  buildShoulderPressUploadUrl,
  clearPendingShoulderPressSession,
  createPendingShoulderPressSession,
  isCompressedShoulderPressSegment,
  loadPendingShoulderPressSession,
  markShoulderPressTrainingEnded,
  markShoulderPressTrainingStarted,
  savePendingShoulderPressSession,
  normalizeShoulderPressExpectedDurationSeconds,
  requireShoulderPressTrainingStartedAt,
  type CompressedShoulderPressSegment,
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

function mediaErrorDetail(error: unknown): string {
  let detail = ''
  if (error instanceof Error) {
    detail = error.message
  } else if (error && typeof error === 'object') {
    const errMsg = (error as { errMsg?: unknown }).errMsg
    if (typeof errMsg === 'string') detail = errMsg
  } else if (typeof error === 'string') {
    detail = error
  }

  return detail.replace(/\s+/g, ' ').trim()
}

function segmentPersistenceErrorMessage(error: unknown): string {
  const detail = mediaErrorDetail(error)
  if (!detail || containsSensitiveCredentialText(detail)) {
    return '录像分段保存失败，请重试'
  }
  return `录像分段保存失败：${detail.slice(0, 180)}`
}

function todayTrainingDate(): string {
  const date = new Date()
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0')
  ].join('-')
}

function expectedDurationSeconds(action: ShoulderPressAction): number {
  return normalizeShoulderPressExpectedDurationSeconds(
    (action.duration_minutes || 1) * 60
  )
}

function updateSegment(
  session: PendingShoulderPressSession,
  index: number,
  update: Partial<CompressedShoulderPressSegment>
): PendingShoulderPressSession {
  return {
    ...session,
    segments: session.segments.map((segment) => (
      segment.index === index && isCompressedShoulderPressSegment(segment)
        ? { ...segment, ...update }
        : segment
    ))
  }
}

function persistSession(session: PendingShoulderPressSession, onSession?: SessionUpdate): PendingShoulderPressSession {
  savePendingShoulderPressSession(Taro, session)
  onSession?.(session)
  return session
}

function persistOwnedSession(
  session: PendingShoulderPressSession,
  onSession?: SessionUpdate
): PendingShoulderPressSession | null {
  const saved = saveOwnedPendingShoulderPressSession(Taro, session)
  if (!saved) return null
  onSession?.(saved)
  return saved
}

function deleteLocalSegmentFile(filePath: string) {
  try {
    Taro.getFileSystemManager().unlink({
      filePath,
      success: () => undefined,
      fail: () => undefined
    })
  } catch {
    // 服务端已确认分段后，本地清理失败不应阻塞后续训练。
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
      if (!isCompressedShoulderPressSegment(segment)) return segment
      if (uploaded.has(segment.index)) return { ...segment, uploadState: 'uploaded' }
      if (segment.uploadState === 'uploading') return { ...segment, uploadState: 'pending', sha256: undefined }
      return segment
    })
  }
}

async function ensureRemoteSession(
  session: PendingShoulderPressSession,
  onSession?: SessionUpdate
): Promise<PendingShoulderPressSession | null> {
  if (session.videoId) return session
  const trainingStartedAt = requireShoulderPressTrainingStartedAt(session)
  const created = await createVideoSession({
    actionId: session.actionId,
    clientSessionId: session.clientSessionId,
    trainingDate: session.trainingDate,
    expectedDurationSeconds: session.expectedDurationSeconds,
    trainingStartedAt
  })
  const latest = loadOwnedPendingShoulderPressSession(Taro, session.clientSessionId)
  if (!latest) return null
  return persistOwnedSession({
    ...mergeServerUploaded(latest, created.uploaded_segments),
    videoId: created.video_id
  }, onSession)
}

async function uploadPendingSegments(onSession?: SessionUpdate): Promise<void> {
  let session = loadPendingShoulderPressSession(Taro)
  if (!session || session.finalized || session.segments.length === 0) return
  if (session.segments.some((segment) => !isCompressedShoulderPressSegment(segment))) return

  const clientSessionId = session.clientSessionId
  session = await ensureRemoteSession(session, onSession)
  if (!session || !session.videoId) return
  const status = await getVideoSessionStatus(session.videoId)
  const latestAfterStatus = loadOwnedPendingShoulderPressSession(Taro, clientSessionId)
  if (!latestAfterStatus) return
  session = persistOwnedSession(mergeServerUploaded({
    ...latestAfterStatus,
    videoId: session.videoId
  }, status.uploaded_segments), onSession)
  if (!session) return

  for (;;) {
    session = loadOwnedPendingShoulderPressSession(Taro, clientSessionId)
    if (!session || session.finalized || !session.videoId) return

    const segment = session.segments.find((item) => (
      isCompressedShoulderPressSegment(item) && item.uploadState !== 'uploaded'
    ))
    if (!segment) return
    if (!isCompressedShoulderPressSegment(segment)) return

    session = persistOwnedSession(updateSegment(session, segment.index, {
      uploadState: 'uploading',
      sha256: undefined
    }), onSession)
    if (!session) return

    try {
      const uploaded = await uploadVideoSegment({
        videoId: session.videoId,
        index: segment.index,
        filePath: segment.savedFilePath,
        durationMs: segment.durationMs,
        sizeBytes: segment.sizeBytes
      })
      session = loadOwnedPendingShoulderPressSession(Taro, clientSessionId)
      if (!session) return
      session = persistOwnedSession(updateSegment(session, uploaded.index, {
        uploadState: 'uploaded',
        sha256: uploaded.sha256
      }), onSession)
      if (!session) return
      deleteLocalSegmentFile(segment.savedFilePath)
    } catch (error) {
      session = loadOwnedPendingShoulderPressSession(Taro, clientSessionId)
      if (!session) return
      const retained = await saveTemporaryShoulderPressSegmentForRetry({
        filePath: segment.savedFilePath,
        localFileState: segment.localFileState ?? 'saved'
      }, (options) => Taro.saveFile(options))
      session = loadOwnedPendingShoulderPressSession(Taro, clientSessionId)
      if (!session) return
      persistOwnedSession({
        ...updateSegment(session, segment.index, {
          savedFilePath: retained.filePath,
          localFileState: retained.localFileState,
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
      const hasPending = latest?.segments.some((segment) => (
        isCompressedShoulderPressSegment(segment) && segment.uploadState !== 'uploaded'
      )) ?? false
      if (completedWithoutError && latest && !latest.finalized && hasPending) {
        void uploadPendingSegmentsInBackground(onSession)
      }
    })
  registerShoulderPressBackgroundUpload(backgroundUploadPromise)

  return backgroundUploadPromise
}

export default function ShoulderPressCameraPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const [action, setAction] = useState<ShoulderPressAction | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [cameraReady, setCameraReady] = useState(false)
  const [recording, setRecording] = useState(false)
  const [paused, setPaused] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [tailSaveFailed, setTailSaveFailed] = useState(false)
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
  const tailSaveFailedRef = useRef(false)
  const hidePauseRequestedRef = useRef(false)
  const mountedRef = useRef(true)
  const keepScreenOnRef = useRef(false)
  const recordingBaseDurationMsRef = useRef(0)
  const recordingStartedAtRef = useRef(0)
  const segmentSaveChainRef = useRef<Promise<void>>(Promise.resolve())

  function syncSession(nextSession: PendingShoulderPressSession) {
    sessionRef.current = nextSession
    if (!mountedRef.current) return
    setSession(nextSession)
    if (nextSession.lastError) setError(nextSession.lastError)
  }

  function saveCurrentSession(nextSession: PendingShoulderPressSession) {
    persistSession(nextSession, syncSession)
  }

  function deleteOrphanedSavedFile(savedFilePath: string) {
    deleteLocalSegmentFile(savedFilePath)
  }

  function resolveOwnedSegmentWriteBase(
    expectedClientSessionId: string
  ): PendingShoulderPressSession | null {
    if (!mountedRef.current) return null

    const currentSession = sessionRef.current
    if (
      !currentSession ||
      currentSession.finalized ||
      currentSession.clientSessionId !== expectedClientSessionId
    ) {
      return null
    }

    const storedSession = loadPendingShoulderPressSession(Taro)
    if (storedSession) {
      if (
        storedSession.finalized ||
        storedSession.clientSessionId !== expectedClientSessionId
      ) {
        return null
      }
      return storedSession
    }

    if (currentSession.segments.length > 0) return null
    return currentSession
  }

  function currentElapsedMs(): number {
    const savedDuration = sessionRef.current?.actualDurationMs ?? session?.actualDurationMs ?? 0
    return computeShoulderPressEffectiveDuration({
      savedDurationMs: savedDuration,
      recording: recordingRef.current,
      recordingBaseDurationMs: recordingBaseDurationMsRef.current,
      recordingStartedAtMs: recordingStartedAtRef.current,
      nowMs: Date.now()
    })
  }

  function setTrainingScreenAwake(keepScreenOn: boolean) {
    if (keepScreenOnRef.current === keepScreenOn) return
    keepScreenOnRef.current = keepScreenOn
    try {
      void Taro.setKeepScreenOn({ keepScreenOn }).catch(() => {
        if (keepScreenOn) keepScreenOnRef.current = false
      })
    } catch {
      if (keepScreenOn) keepScreenOnRef.current = false
    }
  }

  async function persistRecordedSegment(
    tempFilePath: string,
    recordedDurationMs: number
  ): Promise<void> {
    const write = segmentSaveChainRef.current.then(async () => {
      const currentSession = sessionRef.current
      if (!currentSession) throw new Error('训练会话未准备好，请返回处方重新进入')
      const expectedClientSessionId = currentSession.clientSessionId

      let durationMs = Math.max(1, Math.round(recordedDurationMs))
      try {
        const info = await Taro.getVideoInfo({ src: tempFilePath })
        if (Number.isFinite(info.duration) && info.duration > 0) {
          durationMs = Math.max(1, Math.round(info.duration * 1000))
        }
      } catch {
        // iOS 偶尔返回无效媒体时长；录像器计时仍可作为分段时长。
      }
      const fileInfo = await Taro.getFileInfo({ filePath: tempFilePath })
      const sizeBytes = Number(fileInfo.size)
      if (!Number.isInteger(sizeBytes) || sizeBytes <= 0) {
        throw new Error('无法读取录像分段实际大小，请重试')
      }

      let writeBase = resolveOwnedSegmentWriteBase(expectedClientSessionId)
      if (!writeBase) {
        deleteOrphanedSavedFile(tempFilePath)
        return
      }

      const existingSegment = writeBase.segments.find((segment) => (
        isCompressedShoulderPressSegment(segment) &&
        segment.savedFilePath === tempFilePath
      ))
      if (!existingSegment) {
        writeBase = appendUploadableShoulderPressSegment(writeBase, {
          filePath: tempFilePath,
          durationMs,
          sizeBytes,
          localFileState: 'temporary'
        })
        saveCurrentSession(writeBase)
      }
      void uploadPendingSegmentsInBackground(syncSession)
    })

    segmentSaveChainRef.current = write.catch(() => undefined)
    try {
      await write
    } catch (saveError) {
      const message = segmentPersistenceErrorMessage(saveError)
      setError(message)
      throw new Error(message)
    }
  }

  function ensureRecorder(): ShoulderPressRecorder {
    if (recorderRef.current) return recorderRef.current
    const context = cameraContextRef.current ?? Taro.createCameraContext()
    cameraContextRef.current = context
    recorderRef.current = new ShoulderPressRecorder({
      camera: context,
      now: () => Date.now(),
      maxDurationMs: SHOULDER_PRESS_RECORDING_STOP_MS,
      onMaxDuration: () => {
        void finishTraining(true)
      },
      onSegment: (tempFilePath, durationMs) => persistRecordedSegment(tempFilePath, durationMs),
      onPause: () => {
        recordingRef.current = false
        pausedRef.current = true
        recordingBaseDurationMsRef.current = sessionRef.current?.actualDurationMs ?? 0
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
      const currentSession = sessionRef.current
      if (!currentSession) throw new Error('训练会话未准备好，请返回处方重新进入')
      const startedSession = markShoulderPressTrainingStarted(currentSession, Date.now())
      saveCurrentSession(startedSession)
      recordingRef.current = true
      pausedRef.current = false
      recordingBaseDurationMsRef.current = sessionRef.current?.actualDurationMs ?? 0
      recordingStartedAtRef.current = Date.now()
      setTrainingScreenAwake(true)
      setRecording(true)
      setPaused(false)
    } catch (startError) {
      setTrainingScreenAwake(false)
      setError(startError instanceof Error ? startError.message : '摄像头录像启动失败，请检查权限后重试')
    } finally {
      commandInFlightRef.current = false
      setProcessing(false)
      if (hidePauseRequestedRef.current && !finishInFlightRef.current) {
        void pauseTraining()
      }
    }
  }

  async function pauseTraining() {
    if (finishInFlightRef.current) return
    if (commandInFlightRef.current) {
      hidePauseRequestedRef.current = true
      return
    }
    if (!recorderRef.current || !recordingRef.current) {
      hidePauseRequestedRef.current = false
      return
    }
    hidePauseRequestedRef.current = false
    commandInFlightRef.current = true
    setProcessing(true)
    try {
      await recorderRef.current.pause()
    } catch (pauseError) {
      setError(pauseError instanceof Error ? pauseError.message : '暂停录像失败，请稍后重试')
    } finally {
      recordingRef.current = false
      pausedRef.current = true
      recordingBaseDurationMsRef.current = sessionRef.current?.actualDurationMs ?? 0
      recordingStartedAtRef.current = 0
      setTrainingScreenAwake(false)
      setRecording(false)
      setPaused(true)
      commandInFlightRef.current = false
      setProcessing(false)
    }
  }

  async function finishTraining(force = false) {
    if (finishInFlightRef.current || tailSaveFailedRef.current) return
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
      const currentSession = sessionRef.current
      if (!currentSession) throw new Error('训练会话未准备好，请返回处方重新进入')
      const endedSession = markShoulderPressTrainingEnded(currentSession, Date.now())
      saveCurrentSession(endedSession)
      if (recorderRef.current) {
        await recorderRef.current.finish()
      }
      await segmentSaveChainRef.current
      await waitForShoulderPressBackgroundUploadSettled()
      const uploadSession = sessionRef.current
      if (!uploadSession || uploadSession.segments.length === 0) {
        throw new Error('还没有可上传的训练片段，请先开始训练')
      }
      recordingRef.current = false
      pausedRef.current = false
      setRecording(false)
      setPaused(false)
      await Taro.reLaunch({ url: buildShoulderPressUploadUrl() })
    } catch (finishError) {
      if (recorderRef.current?.hasFailedSegment()) {
        tailSaveFailedRef.current = true
        recordingRef.current = false
        pausedRef.current = false
        recordingStartedAtRef.current = 0
        setTailSaveFailed(true)
        setRecording(false)
        setPaused(false)
      }
      setError(finishError instanceof Error ? finishError.message : '训练完成失败，请重试')
    } finally {
      setTrainingScreenAwake(false)
      finishInFlightRef.current = false
      commandInFlightRef.current = false
      setProcessing(false)
    }
  }

  async function retryTailSegment() {
    if (finishInFlightRef.current || commandInFlightRef.current) return
    const recorder = recorderRef.current
    if (!recorder || !tailSaveFailedRef.current) return

    finishInFlightRef.current = true
    commandInFlightRef.current = true
    setProcessing(true)
    setError('')
    try {
      const retried = await recorder.retryFailedSegment()
      await segmentSaveChainRef.current
      if (!retried || recorder.hasFailedSegment()) {
        throw new Error('尾段仍未保存，请重试或重新训练')
      }
      await waitForShoulderPressBackgroundUploadSettled()
      const currentSession = sessionRef.current
      if (!currentSession || currentSession.segments.length === 0) {
        throw new Error('尾段保存后未生成可上传录像，请重新训练')
      }
      tailSaveFailedRef.current = false
      setTailSaveFailed(false)
      await Taro.reLaunch({ url: buildShoulderPressUploadUrl() })
    } catch (retryError) {
      tailSaveFailedRef.current = true
      setTailSaveFailed(true)
      setError(retryError instanceof Error ? retryError.message : '尾段保存失败，请重试或重新训练')
    } finally {
      finishInFlightRef.current = false
      commandInFlightRef.current = false
      setProcessing(false)
    }
  }

  async function restartAfterTailFailure() {
    if (finishInFlightRef.current || commandInFlightRef.current) return
    commandInFlightRef.current = true
    setProcessing(true)
    try {
      setTrainingScreenAwake(false)
      const abandoned = recorderRef.current?.abandonFailedSegment()
      const paths = new Set([
        ...(sessionRef.current?.segments.map((segment) => (
          isCompressedShoulderPressSegment(segment)
            ? segment.savedFilePath
            : segment.rawSavedFilePath
        )) ?? []),
        ...(abandoned?.savedFilePath ? [abandoned.savedFilePath] : [])
      ])
      for (const path of paths) deleteOrphanedSavedFile(path)
      clearPendingShoulderPressSession(Taro)
      sessionRef.current = null
      tailSaveFailedRef.current = false
      setTailSaveFailed(false)
      await Taro.reLaunch({ url: buildShoulderPressSessionUrl(actionId) })
    } finally {
      commandInFlightRef.current = false
      setProcessing(false)
    }
  }

  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      const redirected = await reLaunchPendingShoulderPressUploadIfNeeded(Taro)
      if (cancelled || redirected) return

      if (!Number.isInteger(actionId) || actionId <= 0) {
        setError('训练动作无效，请返回当前处方重新进入')
        setLoaded(true)
        return
      }

      try {
        const prescription = await request<CurrentPrescription>('/patient-app/current-prescription/')
        if (cancelled) return
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
      } catch (loadError) {
        if (cancelled) return
        setError(loadError instanceof Error ? loadError.message : '当前动作加载失败，请稍后重试')
      } finally {
        if (!cancelled) setLoaded(true)
      }
    }

    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [actionId])

  useEffect(() => () => {
    mountedRef.current = false
    setTrainingScreenAwake(false)
  }, [])

  useEffect(() => {
    if (!recording) return undefined
    const stopDelayMs = Math.max(0, SHOULDER_PRESS_RECORDING_STOP_MS - currentElapsedMs())
    const hardStopTimer = setTimeout(() => {
      void finishTraining(true)
    }, stopDelayMs)
    const timer = setInterval(() => {
      const elapsedMs = currentElapsedMs()
      setLiveTick(Date.now())
      if (shouldAutoFinishShoulderPressTraining(elapsedMs)) {
        void finishTraining(true)
      }
    }, 1000)
    return () => {
      clearTimeout(hardStopTimer)
      clearInterval(timer)
    }
  }, [recording])

  useDidHide(() => {
    if (finishInFlightRef.current) return
    hidePauseRequestedRef.current = true
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
      : tailSaveFailed
        ? '尾段尚未保存，不能提交当前录像。'
        : '准备好后点击开始训练。'

  return (
    <View className='page shoulder-press-page'>
      <View className='page-hero shoulder-press-hero'>
        <Text className='eyebrow'>抗阻训练</Text>
        <Text className='title'>{action?.action_name ?? '肩部推举'}</Text>
        <Text className='muted'>前置摄像头会记录动作，请跟随示例缓慢完成。</Text>
      </View>

      <View className='camera-training-stage'>
        <View className='training-media-slot'>
          <Text className='training-media-label'>我的画面</Text>
          <Text className='camera-training-guidance'>请将手机竖直固定，确保上半身和双臂完整入镜。</Text>
          <View className='camera-training-frame'>
            <Camera
              className='camera-preview'
              devicePosition='front'
              resolution='low'
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
      ) : tailSaveFailed ? (
        <View className='button-row shoulder-press-action-row'>
          <Button
            className='primary-button'
            loading={processing}
            disabled={processing}
            onClick={() => void retryTailSegment()}
          >
            重试保存尾段
          </Button>
          <Button
            className='secondary-button'
            loading={processing}
            disabled={processing}
            onClick={() => void restartAfterTailFailure()}
          >
            重新训练
          </Button>
        </View>
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
