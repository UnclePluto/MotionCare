import { Button, Camera, Text, View } from '@tarojs/components'
import Taro, { useDidHide, useDidShow, useRouter } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import { containsSensitiveCredentialText } from '../../api/safeError'
import { fetchCurrentPrescriptionData } from '../../demo/patientAppData'
import { isDemoSession } from '../../demo/session'
import DemoCamera from '../../features/motion-training/DemoCamera'
import {
  createMotionTrainingAlertPlayer,
  MOTION_TRAINING_ALERT_TEXT,
  type MotionTrainingAlertKind,
  type MotionTrainingAlertPlayer
} from '../../features/motion-training/alertAudio'
import {
  canResumeMotionTrainingFromBuffer,
  nextMotionTrainingBufferTransition,
  pendingMotionTrainingLocalBytes,
  type MotionTrainingBufferState
} from '../../features/motion-training/bufferGuard'
import { saveTemporaryMotionTrainingSegmentForRetry } from '../../features/motion-training/localFile'
import {
  canStartMotionTrainingRecording,
  computeMotionTrainingEffectiveDuration,
  loadOwnedPendingMotionTrainingSession,
  registerMotionTrainingBackgroundUpload,
  reLaunchPendingMotionTrainingUploadIfNeeded,
  resolveMotionTrainingAction,
  saveOwnedPendingMotionTrainingSession,
  motionTrainingUploadCounters,
  MOTION_TRAINING_RECORDING_STOP_MS,
  shouldAutoFinishMotionTraining,
  waitForMotionTrainingBackgroundUploadSettled,
  type MotionTrainingAction
} from '../../features/motion-training/pageState'
import { MotionTrainingRecorder } from '../../features/motion-training/recorder'
import { MotionTrainingOverlay } from '../../features/motion-training/TrainingOverlay'
import {
  appendUploadableMotionTrainingSegment,
  buildMotionTrainingSessionUrl,
  buildMotionTrainingUploadUrl,
  clearPendingMotionTrainingSession,
  createPendingMotionTrainingSession,
  isCompressedMotionTrainingSegment,
  loadPendingMotionTrainingSession,
  markMotionTrainingEnded,
  markMotionTrainingStarted,
  promoteLegacyMotionTrainingSegment,
  savePendingMotionTrainingSession,
  normalizeMotionTrainingExpectedDurationSeconds,
  requireMotionTrainingStartedAt,
  type CompressedMotionTrainingSegment,
  type PendingMotionTrainingSession
} from '../../features/motion-training/session'
import {
  createVideoSession,
  getVideoSessionStatus,
  uploadVideoSegment
} from '../../features/motion-training/api'
import {
  cleanupAndCheckMotionTrainingStorage,
  type MotionTrainingSavedFile
} from '../../features/motion-training/storageGuard'

type CameraContext = ReturnType<typeof Taro.createCameraContext>
type SessionUpdate = (session: PendingMotionTrainingSession) => void
type PreflightState = 'idle' | 'checking' | 'blocked' | 'failed'

let backgroundUploadPromise: Promise<void> | null = null

const TRAINING_TOP_GAP_PX = 12
const DEFAULT_TRAINING_TOP_INSET_PX = 24
const DESIGN_WIDTH_RPX = 750
const DEFAULT_WINDOW_WIDTH_PX = 375
const TRAINING_BACK_CONTROL_HEIGHT_RPX = 88
const TRAINING_PREVIEW_HEIGHT_RPX = 300

type TrainingTopLayout = {
  topInset: number
  uploadStatusTop: number
}

function positivePixelValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
    ? value
    : null
}

function designPixels(rpx: number, windowWidth: number): number {
  return rpx * windowWidth / DESIGN_WIDTH_RPX
}

function resolveTrainingTopLayout(): TrainingTopLayout {
  let hasWindowInfo = false
  let windowWidth = DEFAULT_WINDOW_WIDTH_PX
  let safeTop = 0

  try {
    const windowInfo = Taro.getWindowInfo()
    hasWindowInfo = true
    windowWidth = positivePixelValue(windowInfo.windowWidth)
      ?? positivePixelValue(windowInfo.screenWidth)
      ?? DEFAULT_WINDOW_WIDTH_PX
    safeTop = Math.max(
      positivePixelValue(windowInfo.safeArea?.top) ?? 0,
      positivePixelValue(windowInfo.statusBarHeight) ?? 0
    )
  } catch {
    // 窗口信息不可用时，保留默认宽度以放置画中画。
  }

  let menuBottom = 0
  try {
    menuBottom = positivePixelValue(Taro.getMenuButtonBoundingClientRect().bottom) ?? 0
  } catch {
    // 非微信环境或菜单测量暂不可用时，继续使用窗口安全区回退。
  }

  const backControlHeight = designPixels(TRAINING_BACK_CONTROL_HEIGHT_RPX, windowWidth)
  const backControlBottom = hasWindowInfo
    ? safeTop + backControlHeight
    : menuBottom > 0
      ? menuBottom + backControlHeight
      : 0
  const highestTopObstacle = Math.max(menuBottom, backControlBottom)
  const topInset = highestTopObstacle > 0
    ? Math.ceil(highestTopObstacle + TRAINING_TOP_GAP_PX)
    : DEFAULT_TRAINING_TOP_INSET_PX

  return {
    topInset,
    uploadStatusTop: Math.ceil(
      topInset + designPixels(TRAINING_PREVIEW_HEIGHT_RPX, windowWidth) + TRAINING_TOP_GAP_PX
    )
  }
}

function listSavedMotionTrainingFiles(): Promise<MotionTrainingSavedFile[]> {
  const fs = Taro.getFileSystemManager()
  return new Promise((resolve, reject) => {
    fs.getSavedFileList({
      success: (result) => resolve(result.fileList ?? []),
      fail: reject
    })
  })
}

function removeSavedMotionTrainingFile(filePath: string): Promise<void> {
  const fs = Taro.getFileSystemManager()
  return new Promise((resolve, reject) => {
    fs.removeSavedFile({
      filePath,
      success: () => resolve(),
      fail: reject
    })
  })
}

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

function expectedDurationSeconds(action: MotionTrainingAction): number {
  return normalizeMotionTrainingExpectedDurationSeconds(
    (action.duration_minutes || 1) * 60
  )
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

function persistSession(session: PendingMotionTrainingSession, onSession?: SessionUpdate): PendingMotionTrainingSession {
  savePendingMotionTrainingSession(Taro, session)
  onSession?.(session)
  return session
}

function persistOwnedSession(
  session: PendingMotionTrainingSession,
  onSession?: SessionUpdate
): PendingMotionTrainingSession | null {
  const saved = saveOwnedPendingMotionTrainingSession(Taro, session)
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
      if (uploaded.has(segment.index)) {
        return { ...segment, uploadState: 'uploaded' }
      }
      if (segment.uploadState === 'uploading') return { ...segment, uploadState: 'pending', sha256: undefined }
      return segment
    })
  }
}

function newlyConfirmedLocalFiles(
  session: PendingMotionTrainingSession,
  uploadedSegments: number[] | undefined
): string[] {
  const uploaded = new Set(uploadedSegments ?? [])
  return session.segments.flatMap((segment) => (
    isCompressedMotionTrainingSegment(segment) &&
    segment.uploadState !== 'uploaded' &&
    uploaded.has(segment.index)
      ? [segment.savedFilePath]
      : []
  ))
}

function hasUnresolvedMotionTrainingLocalSegment(
  session: PendingMotionTrainingSession
): boolean {
  return session.segments.some((segment) => (
    !isCompressedMotionTrainingSegment(segment) || (
      segment.uploadState !== 'uploaded' && segment.localFileState === 'save_failed'
    )
  ))
}

async function ensureRemoteSession(
  session: PendingMotionTrainingSession,
  onSession?: SessionUpdate
): Promise<PendingMotionTrainingSession | null> {
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
  const confirmedLocalFiles = newlyConfirmedLocalFiles(latest, created.uploaded_segments)
  const saved = persistOwnedSession({
    ...mergeServerUploaded(latest, created.uploaded_segments),
    videoId: created.video_id
  }, onSession)
  if (saved) confirmedLocalFiles.forEach(deleteLocalSegmentFile)
  return saved
}

async function uploadPendingSegments(onSession?: SessionUpdate): Promise<void> {
  let session = loadPendingMotionTrainingSession(Taro)
  if (!session || session.finalized || session.segments.length === 0) return
  if (session.segments.some((segment) => !isCompressedMotionTrainingSegment(segment))) return

  const clientSessionId = session.clientSessionId
  session = await ensureRemoteSession(session, onSession)
  if (!session || !session.videoId) return
  const status = await getVideoSessionStatus(session.videoId)
  const latestAfterStatus = loadOwnedPendingMotionTrainingSession(Taro, clientSessionId)
  if (!latestAfterStatus) return
  const confirmedLocalFiles = newlyConfirmedLocalFiles(
    latestAfterStatus,
    status.uploaded_segments
  )
  session = persistOwnedSession(mergeServerUploaded({
    ...latestAfterStatus,
    videoId: session.videoId
  }, status.uploaded_segments), onSession)
  if (!session) return
  confirmedLocalFiles.forEach(deleteLocalSegmentFile)

  for (;;) {
    session = loadOwnedPendingMotionTrainingSession(Taro, clientSessionId)
    if (!session || session.finalized || !session.videoId) return

    const segment = session.segments.find((item) => (
      isCompressedMotionTrainingSegment(item) && item.uploadState !== 'uploaded'
    ))
    if (!segment) return
    if (!isCompressedMotionTrainingSegment(segment)) return

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
      session = loadOwnedPendingMotionTrainingSession(Taro, clientSessionId)
      if (!session) return
      session = persistOwnedSession(updateSegment(session, uploaded.index, {
        uploadState: 'uploaded',
        sha256: uploaded.sha256
      }), onSession)
      if (!session) return
      deleteLocalSegmentFile(segment.savedFilePath)
    } catch (error) {
      session = loadOwnedPendingMotionTrainingSession(Taro, clientSessionId)
      if (!session) return
      const retained = await saveTemporaryMotionTrainingSegmentForRetry({
        filePath: segment.savedFilePath,
        localFileState: segment.localFileState ?? 'saved'
      }, (options) => Taro.saveFile(options))
      session = loadOwnedPendingMotionTrainingSession(Taro, clientSessionId)
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
      const latest = loadPendingMotionTrainingSession(Taro)
      const hasPending = latest?.segments.some((segment) => (
        isCompressedMotionTrainingSegment(segment) && segment.uploadState !== 'uploaded'
      )) ?? false
      if (completedWithoutError && latest && !latest.finalized && hasPending) {
        void uploadPendingSegmentsInBackground(onSession)
      }
    })
  registerMotionTrainingBackgroundUpload(backgroundUploadPromise)

  return backgroundUploadPromise
}

export function MotionTrainingRecordingCameraPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const [action, setAction] = useState<MotionTrainingAction | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [cameraReady, setCameraReady] = useState(false)
  const [recording, setRecording] = useState(false)
  const [paused, setPaused] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [preflightState, setPreflightState] = useState<PreflightState>('idle')
  const [bufferState, setBufferState] = useState<MotionTrainingBufferState>('recording')
  const [tailSaveFailed, setTailSaveFailed] = useState(false)
  const [session, setSession] = useState<PendingMotionTrainingSession | null>(null)
  const [error, setError] = useState('')
  const [trainingTopLayout] = useState(resolveTrainingTopLayout)
  const [, setLiveTick] = useState(Date.now())
  const cameraContextRef = useRef<CameraContext | null>(null)
  const recorderRef = useRef<MotionTrainingRecorder | null>(null)
  const sessionRef = useRef<PendingMotionTrainingSession | null>(null)
  const recordingRef = useRef(false)
  const pausedRef = useRef(false)
  const commandInFlightRef = useRef(false)
  const preflightInFlightRef = useRef(false)
  const finishInFlightRef = useRef(false)
  const finishPromptInFlightRef = useRef(false)
  const finishAttemptGenerationRef = useRef(0)
  const finishCompletedRef = useRef(false)
  const tailSaveFailedRef = useRef(false)
  const hidePauseRequestedRef = useRef(false)
  const mountedRef = useRef(true)
  const pageVisibleRef = useRef(true)
  const foregroundGenerationRef = useRef(0)
  const bufferStateRef = useRef<MotionTrainingBufferState>('recording')
  const latestPendingBytesRef = useRef(0)
  const bufferPauseQueuedRef = useRef(false)
  const discardRecorderSegmentsRef = useRef(false)
  const alertPlayerRef = useRef<MotionTrainingAlertPlayer | null>(null)
  const keepScreenOnRef = useRef(false)
  const recordingBaseDurationMsRef = useRef(0)
  const recordingStartedAtRef = useRef(0)
  const segmentSaveChainRef = useRef<Promise<void>>(Promise.resolve())

  if (!alertPlayerRef.current) {
    alertPlayerRef.current = createMotionTrainingAlertPlayer()
  }

  function playBufferAlert(kind: MotionTrainingAlertKind) {
    void alertPlayerRef.current?.play(kind).catch(() => false)
  }

  function queueBufferPause() {
    if (bufferPauseQueuedRef.current) return
    bufferPauseQueuedRef.current = true
    void segmentSaveChainRef.current.finally(() => {
      if (!mountedRef.current) {
        bufferPauseQueuedRef.current = false
        return
      }
      void pauseTraining().finally(() => {
        bufferPauseQueuedRef.current = false
      })
    })
  }

  function enterBufferPaused() {
    if (bufferStateRef.current !== 'recording') return
    bufferStateRef.current = 'buffer_paused'
    setBufferState('buffer_paused')
    playBufferAlert('pause')
    queueBufferPause()
  }

  function coordinateBuffer(nextSession: PendingMotionTrainingSession) {
    if (!mountedRef.current) return
    const pendingBytes = pendingMotionTrainingLocalBytes(nextSession.segments)
    latestPendingBytesRef.current = pendingBytes
    const hasUnresolvedLocalSegment = hasUnresolvedMotionTrainingLocalSegment(nextSession)
    if (hasUnresolvedLocalSegment) {
      if (bufferStateRef.current === 'recording') {
        enterBufferPaused()
      } else if (bufferStateRef.current === 'buffer_ready') {
        bufferStateRef.current = 'buffer_paused'
        setBufferState('buffer_paused')
      }
      return
    }

    const transition = nextMotionTrainingBufferTransition({
      state: bufferStateRef.current,
      pendingBytes
    })
    if (transition.state === bufferStateRef.current) return
    bufferStateRef.current = transition.state
    setBufferState(transition.state)
    if (transition.alert) playBufferAlert(transition.alert)
    if (transition.state === 'buffer_paused') queueBufferPause()
  }

  function syncSession(nextSession: PendingMotionTrainingSession) {
    sessionRef.current = nextSession
    if (!mountedRef.current) return
    setSession(nextSession)
    if (nextSession.lastError) setError(nextSession.lastError)
    coordinateBuffer(nextSession)
  }

  function saveCurrentSession(nextSession: PendingMotionTrainingSession) {
    persistSession(nextSession, syncSession)
  }

  function deleteOrphanedSavedFile(savedFilePath: string) {
    deleteLocalSegmentFile(savedFilePath)
  }

  function resolveOwnedSegmentWriteBase(
    expectedClientSessionId: string
  ): PendingMotionTrainingSession | null {
    if (!mountedRef.current) return null

    const currentSession = sessionRef.current
    if (
      !currentSession ||
      currentSession.finalized ||
      currentSession.clientSessionId !== expectedClientSessionId
    ) {
      return null
    }

    const storedSession = loadPendingMotionTrainingSession(Taro)
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
    return computeMotionTrainingEffectiveDuration({
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

  function isForegroundAttemptActive(generation: number): boolean {
    return mountedRef.current &&
      pageVisibleRef.current &&
      foregroundGenerationRef.current === generation
  }

  function appendUnreadableTemporarySegment(
    currentSession: PendingMotionTrainingSession,
    tempFilePath: string,
    durationMs: number,
    failure: unknown
  ): PendingMotionTrainingSession {
    const checked = appendUploadableMotionTrainingSegment(currentSession, {
      filePath: tempFilePath,
      durationMs,
      sizeBytes: 1,
      localFileState: 'save_failed'
    })
    const failedIndex = checked.segments.length - 1
    const message = segmentPersistenceErrorMessage(failure)
    return {
      ...checked,
      segments: checked.segments.map((segment) => (
        segment.index === failedIndex
          ? {
              index: failedIndex,
              compressionState: 'compression_failed' as const,
              rawSavedFilePath: tempFilePath,
              durationMs,
              compressionError: message
            }
          : segment
      )),
      lastError: message
    }
  }

  async function persistRecordedSegment(
    tempFilePath: string,
    recordedDurationMs: number
  ): Promise<void> {
    const discardSegment = discardRecorderSegmentsRef.current
    const write = segmentSaveChainRef.current.then(async () => {
      if (discardSegment) {
        deleteOrphanedSavedFile(tempFilePath)
        return
      }
      const currentSession = sessionRef.current
      if (!currentSession) throw new Error('训练会话未准备好，请返回运动计划重新进入')
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
      let sizeBytes: number
      try {
        const fileInfo = await Taro.getFileInfo({ filePath: tempFilePath })
        sizeBytes = Number('size' in fileInfo ? fileInfo.size : Number.NaN)
        if (!Number.isInteger(sizeBytes) || sizeBytes <= 0) {
          throw new Error('无法读取录像分段实际大小，请重试')
        }
      } catch (fileInfoError) {
        const writeBase = resolveOwnedSegmentWriteBase(expectedClientSessionId)
        if (!writeBase) {
          deleteOrphanedSavedFile(tempFilePath)
          return
        }
        const existingSegment = writeBase.segments.find((segment) => (
          isCompressedMotionTrainingSegment(segment)
            ? segment.savedFilePath === tempFilePath
            : segment.rawSavedFilePath === tempFilePath
        ))
        if (!existingSegment) {
          saveCurrentSession(appendUnreadableTemporarySegment(
            writeBase,
            tempFilePath,
            durationMs,
            fileInfoError
          ))
        }
        throw fileInfoError
      }

      let writeBase = resolveOwnedSegmentWriteBase(expectedClientSessionId)
      if (!writeBase) {
        deleteOrphanedSavedFile(tempFilePath)
        return
      }

      const existingSegment = writeBase.segments.find((segment) => (
        isCompressedMotionTrainingSegment(segment)
          ? segment.savedFilePath === tempFilePath
          : segment.rawSavedFilePath === tempFilePath
      ))
      if (existingSegment && !isCompressedMotionTrainingSegment(existingSegment)) {
        writeBase = promoteLegacyMotionTrainingSegment(writeBase, existingSegment.index, {
          savedFilePath: tempFilePath,
          durationMs,
          sizeBytes,
          localFileState: 'temporary'
        })
        saveCurrentSession(writeBase)
      } else if (!existingSegment) {
        writeBase = appendUploadableMotionTrainingSegment(writeBase, {
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
      if (mountedRef.current) {
        setError(message)
        enterBufferPaused()
      }
      throw new Error(message)
    }
  }

  function ensureRecorder(): MotionTrainingRecorder {
    if (recorderRef.current) return recorderRef.current
    const context = cameraContextRef.current ?? Taro.createCameraContext()
    cameraContextRef.current = context
    recorderRef.current = new MotionTrainingRecorder({
      camera: context,
      now: () => Date.now(),
      maxDurationMs: MOTION_TRAINING_RECORDING_STOP_MS,
      onMaxDuration: (cutoffMs) => {
        void finishTraining(cutoffMs)
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

  async function startRecordingForCurrentSession(foregroundGeneration: number) {
    if (!isForegroundAttemptActive(foregroundGeneration)) return
    const canStart = canStartMotionTrainingRecording({
      actionReady: action !== null && sessionRef.current !== null,
      cameraReady,
      busy: commandInFlightRef.current || finishInFlightRef.current || recordingRef.current
    })
    if (!canStart) {
      setError(action ? '摄像头尚未就绪，请开启权限后再继续训练' : '当前动作不可用，请返回运动计划重新进入')
      return
    }

    commandInFlightRef.current = true
    setProcessing(true)
    setError('')
    try {
      const recorder = ensureRecorder()
      await recorder.start()
      if (!isForegroundAttemptActive(foregroundGeneration)) {
        discardRecorderSegmentsRef.current = true
        try {
          await recorder.pause()
        } catch {
          // 页面已进入后台时以不写入训练开始时间为最高优先级。
        } finally {
          discardRecorderSegmentsRef.current = false
        }
        recordingRef.current = false
        pausedRef.current = false
        recordingStartedAtRef.current = 0
        setTrainingScreenAwake(false)
        setRecording(false)
        setPaused(false)
        return
      }
      const currentSession = sessionRef.current
      if (!currentSession) throw new Error('训练会话未准备好，请返回运动计划重新进入')
      const startedAtMs = Date.now()
      const startedSession = markMotionTrainingStarted(currentSession, startedAtMs)
      syncSession(startedSession)
      try {
        savePendingMotionTrainingSession(Taro, startedSession)
      } catch (persistenceError) {
        try {
          await recorder.finish()
          recordingRef.current = false
          pausedRef.current = false
          recordingBaseDurationMsRef.current = sessionRef.current?.actualDurationMs ?? 0
          recordingStartedAtRef.current = 0
          setRecording(false)
          setPaused(false)
        } catch (compensationError) {
          if (recorder.hasFailedSegment()) {
            tailSaveFailedRef.current = true
            recordingRef.current = false
            pausedRef.current = false
            recordingStartedAtRef.current = 0
            setTailSaveFailed(true)
            setRecording(false)
            setPaused(false)
          } else {
            recordingRef.current = true
            pausedRef.current = false
            recordingBaseDurationMsRef.current = startedSession.actualDurationMs
            recordingStartedAtRef.current = startedAtMs
            setTrainingScreenAwake(true)
            setRecording(true)
            setPaused(false)
          }
          throw compensationError
        }
        throw persistenceError
      }
      recordingRef.current = true
      pausedRef.current = false
      bufferStateRef.current = 'recording'
      recordingBaseDurationMsRef.current = sessionRef.current?.actualDurationMs ?? 0
      recordingStartedAtRef.current = startedAtMs
      setTrainingScreenAwake(true)
      setRecording(true)
      setPaused(false)
      setBufferState('recording')
    } catch (startError) {
      if (!recordingRef.current) setTrainingScreenAwake(false)
      setError(startError instanceof Error ? startError.message : '摄像头录像启动失败，请检查权限后重试')
    } finally {
      commandInFlightRef.current = false
      setProcessing(false)
      if (hidePauseRequestedRef.current && !finishInFlightRef.current) {
        void pauseTraining()
      }
    }
  }

  async function prepareAndStartTraining() {
    if (preflightInFlightRef.current || commandInFlightRef.current || finishInFlightRef.current) return
    if (!action || !cameraReady) {
      setError(action ? '摄像头尚未就绪，请开启权限后再继续训练' : '当前动作不可用，请返回运动计划重新进入')
      return
    }

    const foregroundGeneration = foregroundGenerationRef.current
    preflightInFlightRef.current = true
    setProcessing(true)
    setPreflightState('checking')
    setError('')
    try {
      const result = await cleanupAndCheckMotionTrainingStorage({
        hasPendingSession: () => Boolean(loadPendingMotionTrainingSession(Taro)),
        listSavedFiles: listSavedMotionTrainingFiles,
        removeSavedFile: removeSavedMotionTrainingFile,
        isActive: () => isForegroundAttemptActive(foregroundGeneration)
      })
      if (!isForegroundAttemptActive(foregroundGeneration) || result.kind === 'cancelled') return
      if (result.kind === 'pending_session') {
        await Taro.reLaunch({ url: buildMotionTrainingUploadUrl() })
        return
      }
      if (result.kind === 'blocked') {
        setPreflightState('blocked')
        return
      }

      const reusableSession = sessionRef.current?.trainingStartedAt
        ? sessionRef.current
        : null
      const nextSession = reusableSession ?? createPendingMotionTrainingSession({
        actionId,
        expectedDurationSeconds: expectedDurationSeconds(action),
        trainingDate: todayTrainingDate()
      })
      sessionRef.current = nextSession
      setSession(nextSession)
      setPreflightState('idle')
      setProcessing(false)
      if (!isForegroundAttemptActive(foregroundGeneration)) return
      await startRecordingForCurrentSession(foregroundGeneration)
    } catch {
      if (!mountedRef.current) return
      setPreflightState('failed')
      setError('无法检查录像空间，请重试')
    } finally {
      preflightInFlightRef.current = false
      if (mountedRef.current) {
        setProcessing(false)
        if (hidePauseRequestedRef.current && !commandInFlightRef.current && !finishInFlightRef.current) {
          void pauseTraining()
        }
      }
    }
  }

  async function resumeTrainingAfterBufferReady() {
    if (bufferStateRef.current === 'buffer_paused') return
    if (bufferStateRef.current === 'buffer_ready') {
      const latest = loadPendingMotionTrainingSession(Taro) ?? sessionRef.current
      if (!latest) return
      const pendingBytes = pendingMotionTrainingLocalBytes(latest.segments)
      latestPendingBytesRef.current = pendingBytes
      if (
        hasUnresolvedMotionTrainingLocalSegment(latest) ||
        !canResumeMotionTrainingFromBuffer(pendingBytes)
      ) {
        bufferStateRef.current = 'buffer_paused'
        setBufferState('buffer_paused')
        return
      }
      syncSession(latest)
    }
    await startRecordingForCurrentSession(foregroundGenerationRef.current)
  }

  async function pauseTraining() {
    if (finishInFlightRef.current) return
    if (preflightInFlightRef.current || commandInFlightRef.current) {
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
    let shouldFinishAfterPause = false
    try {
      await recorderRef.current.pause()
      const pausedSession = sessionRef.current
      shouldFinishAfterPause = Boolean(pausedSession) && shouldAutoFinishMotionTraining({
        actualDurationMs: pausedSession?.actualDurationMs ?? 0,
        expectedDurationSeconds: pausedSession?.expectedDurationSeconds ?? 1
      })
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
    if (shouldFinishAfterPause) {
      await finishTraining()
    }
  }

  async function finishTraining(endedAtMs = Date.now()) {
    if (finishCompletedRef.current || finishInFlightRef.current || tailSaveFailedRef.current) return

    finishAttemptGenerationRef.current += 1
    finishInFlightRef.current = true
    commandInFlightRef.current = true
    setProcessing(true)
    setError('')
    try {
      const currentSession = sessionRef.current
      if (!currentSession) throw new Error('训练会话未准备好，请返回运动计划重新进入')
      try {
        const endedSession = markMotionTrainingEnded(currentSession, endedAtMs)
        syncSession(endedSession)
        savePendingMotionTrainingSession(Taro, endedSession)
      } catch {
        // 训练结束时间是可选审计字段，写入失败不能阻止录像停止与上传。
      }
      if (recorderRef.current) {
        await recorderRef.current.finish()
      }
      await segmentSaveChainRef.current
      await waitForMotionTrainingBackgroundUploadSettled()
      const uploadSession = sessionRef.current
      if (!uploadSession || uploadSession.segments.length === 0) {
        throw new Error('还没有可上传的训练片段，请先开始训练')
      }
      recordingRef.current = false
      pausedRef.current = false
      setRecording(false)
      setPaused(false)
      await Taro.reLaunch({ url: buildMotionTrainingUploadUrl() })
      finishCompletedRef.current = true
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

  async function requestManualFinishTraining() {
    if (
      finishCompletedRef.current ||
      finishInFlightRef.current ||
      commandInFlightRef.current ||
      finishPromptInFlightRef.current
    ) return
    const finishAttemptGeneration = finishAttemptGenerationRef.current
    finishPromptInFlightRef.current = true
    try {
      const result = await Taro.showModal({
        title: '结束训练？',
        content: `确认结束本次${action?.action_name ?? '动作'}训练吗？`,
        confirmText: '结束训练',
        confirmColor: '#ff4d4f',
        cancelText: '继续训练'
      })
      if (
        !result.confirm ||
        finishCompletedRef.current ||
        finishAttemptGeneration !== finishAttemptGenerationRef.current
      ) return
      await finishTraining()
    } catch {
      if (
        mountedRef.current &&
        !finishCompletedRef.current &&
        finishAttemptGeneration === finishAttemptGenerationRef.current
      ) {
        setError('结束确认失败，请继续训练或稍后重试')
      }
    } finally {
      finishPromptInFlightRef.current = false
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
      await waitForMotionTrainingBackgroundUploadSettled()
      const currentSession = sessionRef.current
      if (!currentSession || currentSession.segments.length === 0) {
        throw new Error('尾段保存后未生成可上传录像，请重新训练')
      }
      tailSaveFailedRef.current = false
      setTailSaveFailed(false)
      await Taro.reLaunch({ url: buildMotionTrainingUploadUrl() })
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
          isCompressedMotionTrainingSegment(segment)
            ? segment.savedFilePath
            : segment.rawSavedFilePath
        )) ?? []),
        ...(abandoned?.savedFilePath ? [abandoned.savedFilePath] : [])
      ])
      for (const path of paths) deleteOrphanedSavedFile(path)
      clearPendingMotionTrainingSession(Taro)
      sessionRef.current = null
      tailSaveFailedRef.current = false
      setTailSaveFailed(false)
      await Taro.reLaunch({ url: buildMotionTrainingSessionUrl(actionId) })
    } finally {
      commandInFlightRef.current = false
      setProcessing(false)
    }
  }

  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      const redirected = await reLaunchPendingMotionTrainingUploadIfNeeded(Taro)
      if (cancelled || redirected) return

      if (!Number.isInteger(actionId) || actionId <= 0) {
        setError('训练动作无效，请返回当前运动计划重新进入')
        setLoaded(true)
        return
      }

      try {
        const prescription = await fetchCurrentPrescriptionData()
        if (cancelled) return
        const currentAction = resolveMotionTrainingAction(prescription, actionId)
        setAction(currentAction)
        if (!currentAction) {
          setError('动作已失效或运动计划已更新，请返回当前运动计划重新进入')
          return
        }
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
    alertPlayerRef.current?.dispose()
    setTrainingScreenAwake(false)
  }, [])

  useEffect(() => {
    if (!recording) return undefined
    const stopDelayMs = Math.max(0, MOTION_TRAINING_RECORDING_STOP_MS - currentElapsedMs())
    const hardStopTimer = setTimeout(() => {
      void finishTraining()
    }, stopDelayMs)
    const timer = setInterval(() => {
      const elapsedMs = currentElapsedMs()
      setLiveTick(Date.now())
      if (shouldAutoFinishMotionTraining({
        actualDurationMs: elapsedMs,
        expectedDurationSeconds: sessionRef.current?.expectedDurationSeconds ?? 1
      })) {
        void finishTraining()
      }
    }, 1000)
    return () => {
      clearTimeout(hardStopTimer)
      clearInterval(timer)
    }
  }, [recording])

  useDidHide(() => {
    pageVisibleRef.current = false
    foregroundGenerationRef.current += 1
    if (finishInFlightRef.current) return
    hidePauseRequestedRef.current = true
    void pauseTraining()
  })

  useDidShow(() => {
    pageVisibleRef.current = true
    if (
      bufferStateRef.current !== 'buffer_paused' &&
      bufferStateRef.current !== 'buffer_ready'
    ) return
    const latest = loadPendingMotionTrainingSession(Taro)
    if (latest) {
      syncSession(latest)
      void uploadPendingSegmentsInBackground(syncSession)
    }
  })

  const elapsedMs = currentElapsedMs()
  const counters = motionTrainingUploadCounters(session?.segments ?? [])
  const canStartInitial = canStartMotionTrainingRecording({
    actionReady: action !== null,
    cameraReady,
    busy: processing || recording || preflightState === 'checking'
  })
  const preflightMessage = preflightState === 'checking'
    ? '正在清理录像空间，请稍候…'
    : preflightState === 'blocked'
      ? '录像空间不足，至少需要 65 MB 可用空间。'
      : preflightState === 'failed'
        ? '无法检查录像空间，请重试'
        : ''
  const bufferMessage = bufferState === 'buffer_paused'
    ? MOTION_TRAINING_ALERT_TEXT.pause
    : bufferState === 'buffer_ready'
      ? MOTION_TRAINING_ALERT_TEXT.ready
      : ''
  const bufferPaused = bufferState === 'buffer_paused'
  const bufferReady = bufferState === 'buffer_ready'

  return (
    <View className='training-camera-page'>
      <Camera
        className='training-camera-fullscreen'
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

      <View className='training-camera-safe-top'>
        <View className='training-camera-back' onClick={() => Taro.navigateBack({ delta: 1 })}>
          ‹
        </View>
      </View>

      <MotionTrainingOverlay
        videoUrl={action && !action.video_unavailable ? action.video_url : null}
        elapsedMs={elapsedMs}
        expectedDurationSeconds={session?.expectedDurationSeconds ?? (
          action ? expectedDurationSeconds(action) : 1
        )}
        started={Boolean(session?.trainingStartedAt)}
        topInset={trainingTopLayout.topInset}
      />

      {preflightMessage ? (
        <View className='training-preflight-overlay'>
          <Text className='training-preflight-message'>{preflightMessage}</Text>
          {preflightState === 'blocked' || preflightState === 'failed' ? (
            <View className='training-preflight-actions'>
              <Button
                className='camera-start-button'
                disabled={processing}
                onClick={() => void prepareAndStartTraining()}
              >
                重新清理
              </Button>
              <Button
                className='training-preflight-back'
                onClick={() => Taro.reLaunch({ url: '/pages/prescription/index' })}
              >
                返回运动计划
              </Button>
            </View>
          ) : null}
        </View>
      ) : null}

      {bufferMessage ? (
        <View className='training-buffer-banner'>
          <Text>{bufferMessage}</Text>
        </View>
      ) : null}

      {session?.segments.length ? (
        <View
          className='training-upload-status'
          style={{ top: `${trainingTopLayout.uploadStatusTop}px` }}
        >
          <Text>分段上传 {counters.uploaded}/{counters.total}</Text>
        </View>
      ) : null}

      {!loaded ? <Text className='training-camera-loading'>正在加载当前动作</Text> : null}
      {error ? <Text className='camera-error'>{error}</Text> : null}

      <View className='training-camera-bottom-action'>
        {!action && loaded ? (
          <Button
            className='training-secondary-button'
            onClick={() => Taro.reLaunch({ url: '/pages/prescription/index' })}
          >
            返回当前运动计划
          </Button>
        ) : tailSaveFailed ? (
          <>
            <Button
              className='camera-start-button'
              loading={processing}
              disabled={processing}
              onClick={() => void retryTailSegment()}
            >
              重试保存尾段
            </Button>
            <Button
              className='training-secondary-button'
              loading={processing}
              disabled={processing}
              onClick={() => void restartAfterTailFailure()}
            >
              重新训练
            </Button>
          </>
        ) : bufferPaused ? (
          <>
            <Button className='camera-start-button' disabled>等待上传</Button>
            <Button
              className='camera-stop-button'
              disabled={processing || !session?.trainingStartedAt}
              onClick={() => void requestManualFinishTraining()}
            >
              结束训练
            </Button>
          </>
        ) : bufferReady || paused ? (
          <>
            <Button
              className='camera-start-button'
              loading={processing}
              disabled={processing || !cameraReady}
              onClick={() => void resumeTrainingAfterBufferReady()}
            >
              继续训练
            </Button>
            <Button
              className='camera-stop-button'
              loading={processing}
              disabled={processing || !session?.trainingStartedAt}
              onClick={() => void requestManualFinishTraining()}
            >
              结束训练
            </Button>
          </>
        ) : recording ? (
          <Button
            className='camera-stop-button'
            loading={processing}
            disabled={processing || !session?.trainingStartedAt}
            onClick={() => void requestManualFinishTraining()}
          >
            结束训练
          </Button>
        ) : (
          <Button
            className='camera-start-button'
            loading={processing}
            disabled={!canStartInitial}
            onClick={() => void prepareAndStartTraining()}
          >
            开始训练
          </Button>
        )}
      </View>
    </View>
  )
}

export default function MotionTrainingCameraPage() {
  return isDemoSession()
    ? <DemoCamera />
    : <MotionTrainingRecordingCameraPage />
}
