import { Button, Camera, Text, View } from '@tarojs/components'
import Taro, { useDidHide, useDidShow, useRouter } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import { request } from '../../api/client'
import { containsSensitiveCredentialText } from '../../api/safeError'
import type { CurrentPrescription } from '../../types/patientApp'
import './assets/audio/network_slow_paused.m4a'
import './assets/audio/upload_recovered.m4a'
import {
  createShoulderPressAlertPlayer,
  SHOULDER_PRESS_ALERT_TEXT,
  type ShoulderPressAlertKind,
  type ShoulderPressAlertPlayer
} from './alertAudio'
import {
  canResumeShoulderPressFromBuffer,
  nextShoulderPressBufferTransition,
  pendingShoulderPressLocalBytes,
  type ShoulderPressBufferState
} from './bufferGuard'
import { saveTemporaryShoulderPressSegmentForRetry } from './localFile'
import {
  canStartShoulderPressRecording,
  computeShoulderPressEffectiveDuration,
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
import { ShoulderPressTrainingOverlay } from './trainingOverlay'
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
  promoteLegacyShoulderPressSegment,
  savePendingShoulderPressSession,
  normalizeShoulderPressExpectedDurationSeconds,
  requireShoulderPressTrainingStartedAt,
  type CompressedShoulderPressSegment,
  type PendingShoulderPressSession
} from './session'
import {
  createVideoSession,
  getVideoSessionStatus,
  uploadVideoSegment
} from './api'
import {
  cleanupAndCheckShoulderPressStorage,
  type ShoulderPressSavedFile
} from './storageGuard'

type CameraContext = ReturnType<typeof Taro.createCameraContext>
type SessionUpdate = (session: PendingShoulderPressSession) => void
type PreflightState = 'idle' | 'checking' | 'blocked' | 'failed'

let backgroundUploadPromise: Promise<void> | null = null

function listSavedShoulderPressFiles(): Promise<ShoulderPressSavedFile[]> {
  const fs = Taro.getFileSystemManager()
  return new Promise((resolve, reject) => {
    fs.getSavedFileList({
      success: (result) => resolve(result.fileList ?? []),
      fail: reject
    })
  })
}

function removeSavedShoulderPressFile(filePath: string): Promise<void> {
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
      if (uploaded.has(segment.index)) {
        return { ...segment, uploadState: 'uploaded' }
      }
      if (segment.uploadState === 'uploading') return { ...segment, uploadState: 'pending', sha256: undefined }
      return segment
    })
  }
}

function newlyConfirmedLocalFiles(
  session: PendingShoulderPressSession,
  uploadedSegments: number[] | undefined
): string[] {
  const uploaded = new Set(uploadedSegments ?? [])
  return session.segments.flatMap((segment) => (
    isCompressedShoulderPressSegment(segment) &&
    segment.uploadState !== 'uploaded' &&
    uploaded.has(segment.index)
      ? [segment.savedFilePath]
      : []
  ))
}

function hasUnresolvedShoulderPressLocalSegment(
  session: PendingShoulderPressSession
): boolean {
  return session.segments.some((segment) => (
    !isCompressedShoulderPressSegment(segment) || (
      segment.uploadState !== 'uploaded' && segment.localFileState === 'save_failed'
    )
  ))
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
  const confirmedLocalFiles = newlyConfirmedLocalFiles(latest, created.uploaded_segments)
  const saved = persistOwnedSession({
    ...mergeServerUploaded(latest, created.uploaded_segments),
    videoId: created.video_id
  }, onSession)
  if (saved) confirmedLocalFiles.forEach(deleteLocalSegmentFile)
  return saved
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
  const [preflightState, setPreflightState] = useState<PreflightState>('idle')
  const [bufferState, setBufferState] = useState<ShoulderPressBufferState>('recording')
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
  const bufferStateRef = useRef<ShoulderPressBufferState>('recording')
  const latestPendingBytesRef = useRef(0)
  const bufferPauseQueuedRef = useRef(false)
  const discardRecorderSegmentsRef = useRef(false)
  const alertPlayerRef = useRef<ShoulderPressAlertPlayer | null>(null)
  const keepScreenOnRef = useRef(false)
  const recordingBaseDurationMsRef = useRef(0)
  const recordingStartedAtRef = useRef(0)
  const segmentSaveChainRef = useRef<Promise<void>>(Promise.resolve())

  if (!alertPlayerRef.current) {
    alertPlayerRef.current = createShoulderPressAlertPlayer()
  }

  function playBufferAlert(kind: ShoulderPressAlertKind) {
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

  function coordinateBuffer(nextSession: PendingShoulderPressSession) {
    if (!mountedRef.current) return
    const pendingBytes = pendingShoulderPressLocalBytes(nextSession.segments)
    latestPendingBytesRef.current = pendingBytes
    const hasUnresolvedLocalSegment = hasUnresolvedShoulderPressLocalSegment(nextSession)
    if (hasUnresolvedLocalSegment) {
      if (bufferStateRef.current === 'recording') {
        enterBufferPaused()
      } else if (bufferStateRef.current === 'buffer_ready') {
        bufferStateRef.current = 'buffer_paused'
        setBufferState('buffer_paused')
      }
      return
    }

    const transition = nextShoulderPressBufferTransition({
      state: bufferStateRef.current,
      pendingBytes
    })
    if (transition.state === bufferStateRef.current) return
    bufferStateRef.current = transition.state
    setBufferState(transition.state)
    if (transition.alert) playBufferAlert(transition.alert)
    if (transition.state === 'buffer_paused') queueBufferPause()
  }

  function syncSession(nextSession: PendingShoulderPressSession) {
    sessionRef.current = nextSession
    if (!mountedRef.current) return
    setSession(nextSession)
    if (nextSession.lastError) setError(nextSession.lastError)
    coordinateBuffer(nextSession)
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

  function isForegroundAttemptActive(generation: number): boolean {
    return mountedRef.current &&
      pageVisibleRef.current &&
      foregroundGenerationRef.current === generation
  }

  function appendUnreadableTemporarySegment(
    currentSession: PendingShoulderPressSession,
    tempFilePath: string,
    durationMs: number,
    failure: unknown
  ): PendingShoulderPressSession {
    const checked = appendUploadableShoulderPressSegment(currentSession, {
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
          isCompressedShoulderPressSegment(segment)
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
        isCompressedShoulderPressSegment(segment)
          ? segment.savedFilePath === tempFilePath
          : segment.rawSavedFilePath === tempFilePath
      ))
      if (existingSegment && !isCompressedShoulderPressSegment(existingSegment)) {
        writeBase = promoteLegacyShoulderPressSegment(writeBase, existingSegment.index, {
          savedFilePath: tempFilePath,
          durationMs,
          sizeBytes,
          localFileState: 'temporary'
        })
        saveCurrentSession(writeBase)
      } else if (!existingSegment) {
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
      if (mountedRef.current) {
        setError(message)
        enterBufferPaused()
      }
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
      if (!currentSession) throw new Error('训练会话未准备好，请返回处方重新进入')
      const startedAtMs = Date.now()
      const startedSession = markShoulderPressTrainingStarted(currentSession, startedAtMs)
      syncSession(startedSession)
      try {
        savePendingShoulderPressSession(Taro, startedSession)
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
      setError(action ? '摄像头尚未就绪，请开启权限后再继续训练' : '当前动作不可用，请返回处方重新进入')
      return
    }

    const foregroundGeneration = foregroundGenerationRef.current
    preflightInFlightRef.current = true
    setProcessing(true)
    setPreflightState('checking')
    setError('')
    try {
      const result = await cleanupAndCheckShoulderPressStorage({
        hasPendingSession: () => Boolean(loadPendingShoulderPressSession(Taro)),
        listSavedFiles: listSavedShoulderPressFiles,
        removeSavedFile: removeSavedShoulderPressFile,
        isActive: () => isForegroundAttemptActive(foregroundGeneration)
      })
      if (!isForegroundAttemptActive(foregroundGeneration) || result.kind === 'cancelled') return
      if (result.kind === 'pending_session') {
        await Taro.reLaunch({ url: buildShoulderPressUploadUrl() })
        return
      }
      if (result.kind === 'blocked') {
        setPreflightState('blocked')
        return
      }

      const reusableSession = sessionRef.current?.trainingStartedAt
        ? sessionRef.current
        : null
      const nextSession = reusableSession ?? createPendingShoulderPressSession({
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
      const latest = loadPendingShoulderPressSession(Taro) ?? sessionRef.current
      if (!latest) return
      const pendingBytes = pendingShoulderPressLocalBytes(latest.segments)
      latestPendingBytesRef.current = pendingBytes
      if (
        hasUnresolvedShoulderPressLocalSegment(latest) ||
        !canResumeShoulderPressFromBuffer(pendingBytes)
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
      shouldFinishAfterPause = Boolean(pausedSession) && shouldAutoFinishShoulderPressTraining({
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
      if (!currentSession) throw new Error('训练会话未准备好，请返回处方重新进入')
      try {
        const endedSession = markShoulderPressTrainingEnded(currentSession, endedAtMs)
        syncSession(endedSession)
        savePendingShoulderPressSession(Taro, endedSession)
      } catch {
        // 训练结束时间是可选审计字段，写入失败不能阻止录像停止与上传。
      }
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
        content: '确认结束本次肩部推举训练吗？',
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
    const stopDelayMs = Math.max(0, SHOULDER_PRESS_RECORDING_STOP_MS - currentElapsedMs())
    const hardStopTimer = setTimeout(() => {
      void finishTraining()
    }, stopDelayMs)
    const timer = setInterval(() => {
      const elapsedMs = currentElapsedMs()
      setLiveTick(Date.now())
      if (shouldAutoFinishShoulderPressTraining({
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
    const latest = loadPendingShoulderPressSession(Taro)
    if (latest) {
      syncSession(latest)
      void uploadPendingSegmentsInBackground(syncSession)
    }
  })

  const elapsedMs = currentElapsedMs()
  const counters = shoulderPressUploadCounters(session?.segments ?? [])
  const canStartInitial = canStartShoulderPressRecording({
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
    ? SHOULDER_PRESS_ALERT_TEXT.pause
    : bufferState === 'buffer_ready'
      ? SHOULDER_PRESS_ALERT_TEXT.ready
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

      <ShoulderPressTrainingOverlay
        videoUrl={action?.video_url ?? null}
        elapsedMs={elapsedMs}
        expectedDurationSeconds={session?.expectedDurationSeconds ?? (
          action ? expectedDurationSeconds(action) : 1
        )}
        started={Boolean(session?.trainingStartedAt)}
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
                返回处方
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
        <View className='training-upload-status'>
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
            返回当前处方
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
