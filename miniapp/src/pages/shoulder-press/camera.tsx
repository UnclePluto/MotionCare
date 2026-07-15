import { Button, Camera, Text, View } from '@tarojs/components'
import Taro, { useDidHide, useDidShow, useRouter } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import {
  createShoulderPressVideoSession,
  uploadShoulderPressSegment,
} from './api'
import { SegmentQueueRunner } from './segmentQueue'
import {
  classifyTimedOutSegment,
  shouldStartRecordingAfterSessionCreated,
  shouldWaitForAutomaticFinalSegment,
  waitForPendingPersistence,
} from './recordingMachine'
import {
  buildShoulderPressUploadUrl,
  loadShoulderPressSession,
  saveShoulderPressSession,
  type PendingShoulderPressSegment,
  type ShoulderPressSession,
} from './session'

const SEGMENT_DURATION_SECONDS = 30
const STOP_RECORD_TIMEOUT_MS = 10_000

type CameraPosition = 'front' | 'back'

function displayDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, '0')
  const remainder = (seconds % 60).toString().padStart(2, '0')
  return `${minutes}:${remainder}`
}

function localDate(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60_000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

function removeSavedFile(filePath: string): Promise<void> {
  return new Promise((resolve, reject) => {
    Taro.getFileSystemManager().unlink({
      filePath,
      success: () => resolve(),
      fail: (reason) => {
        if (reason.errMsg?.includes('no such file')) resolve()
        else reject(new Error(reason.errMsg || '删除本地视频分片失败'))
      },
    })
  })
}

export default function ShoulderPressCameraPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const [cameraAllowed, setCameraAllowed] = useState(false)
  const [cameraPosition, setCameraPosition] = useState<CameraPosition>('front')
  const [countdown, setCountdown] = useState<number | null>(null)
  const [preparing, setPreparing] = useState(false)
  const [recording, setRecording] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [error, setError] = useState('')
  const countdownTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const recordingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const stopTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cameraContextRef = useRef<ReturnType<typeof Taro.createCameraContext> | null>(null)
  const queueRunnerRef = useRef<SegmentQueueRunner | null>(null)
  const pendingPersistenceRef = useRef(new Set<Promise<void>>())
  const finalCompletionRef = useRef<Promise<void> | null>(null)
  const handledSequencesRef = useRef(new Set<number>())
  const currentSequenceRef = useRef(0)
  const segmentStartedAtRef = useRef(0)
  const elapsedRef = useRef(0)
  const recordingRef = useRef(false)
  const finalizingRef = useRef(false)
  const pageHiddenRef = useRef(false)

  if (!queueRunnerRef.current) {
    queueRunnerRef.current = new SegmentQueueRunner({
      storage: Taro,
      upload: ({ videoId, segment }) => uploadShoulderPressSegment({
        videoId,
        sequenceIndex: segment.sequenceIndex,
        durationSeconds: segment.durationSeconds,
        filePath: segment.savedFilePath,
      }),
      removeFile: removeSavedFile,
    })
  }

  useEffect(() => {
    void Taro.setKeepScreenOn({ keepScreenOn: true })
    Taro.authorize({ scope: 'scope.camera' })
      .then(() => setCameraAllowed(true))
      .catch(() => setError('需要摄像头权限才能开始训练'))

    return () => {
      if (countdownTimerRef.current) clearInterval(countdownTimerRef.current)
      if (recordingTimerRef.current) clearInterval(recordingTimerRef.current)
      if (stopTimeoutRef.current) clearTimeout(stopTimeoutRef.current)
      void Taro.setKeepScreenOn({ keepScreenOn: false })
    }
  }, [])

  useDidShow(() => {
    pageHiddenRef.current = false
    const session = loadShoulderPressSession(Taro)
    if (session && session.phase !== 'recording') {
      void Taro.redirectTo({ url: buildShoulderPressUploadUrl() })
    }
  })

  useDidHide(() => {
    pageHiddenRef.current = true
    if (countdownTimerRef.current) {
      clearInterval(countdownTimerRef.current)
      countdownTimerRef.current = null
      setCountdown(null)
    }
    if (recordingRef.current && !finalizingRef.current) stopRecording('hidden')
  })

  function trackPersistence(promise: Promise<void>) {
    pendingPersistenceRef.current.add(promise)
    void promise
      .finally(() => pendingPersistenceRef.current.delete(promise))
      .catch(() => undefined)
  }

  async function persistSegment(
    tempVideoPath: string,
    sequenceIndex: number,
    durationSeconds: number,
  ) {
    if (!tempVideoPath) throw new Error('未获取到录像分片')
    const session = loadShoulderPressSession(Taro)
    if (!session) throw new Error('训练录像会话已丢失')
    if (session.segments.some((item) => item.sequenceIndex === sequenceIndex)) return
    const saved = await Taro.saveFile({ tempFilePath: tempVideoPath })
    if (!('savedFilePath' in saved)) throw new Error('无法持久保存录像分片')
    const file = await Taro.getFileInfo({ filePath: saved.savedFilePath })
    if (!('size' in file)) throw new Error('无法读取录像分片')
    const segment: PendingShoulderPressSegment = {
      sequenceIndex,
      savedFilePath: saved.savedFilePath,
      durationSeconds,
      sizeBytes: file.size,
      status: 'pending',
      retryCount: 0,
    }
    const latest = loadShoulderPressSession(Taro)
    if (!latest) throw new Error('训练录像会话已丢失')
    saveShoulderPressSession(Taro, {
      ...latest,
      durationSeconds: Math.max(latest.durationSeconds, elapsedRef.current),
      segmentCount: Math.max(latest.segmentCount ?? 0, sequenceIndex + 1),
      segments: [...latest.segments, segment].sort(
        (left, right) => left.sequenceIndex - right.sequenceIndex,
      ),
    })
    void queueRunnerRef.current?.drainAvailable()
  }

  function startRecordingTimer() {
    if (recordingTimerRef.current) return
    recordingTimerRef.current = setInterval(() => {
      elapsedRef.current += 1
      setElapsedSeconds(elapsedRef.current)
      const session = loadShoulderPressSession(Taro)
      if (session) {
        saveShoulderPressSession(Taro, {
          ...session,
          durationSeconds: elapsedRef.current,
        })
      }
    }, 1000)
  }

  function handlePersistenceFailure(reason: unknown) {
    const message = reason instanceof Error ? reason.message : '录像分片保存失败'
    setError(message)
    const session = loadShoulderPressSession(Taro)
    if (session) {
      saveShoulderPressSession(Taro, {
        ...session,
        unrecoverableReason: message,
      })
    }
    if (recordingRef.current && !finalizingRef.current) stopRecording('manual')
  }

  function handleTimedOutSegment(tempVideoPath: string) {
    const completedSequence = currentSequenceRef.current
    if (classifyTimedOutSegment({
      finalizing: finalizingRef.current,
      pageHidden: pageHiddenRef.current,
    }) === 'finalize') {
      recordingRef.current = false
      setRecording(false)
      void finalizeCompletedSegment(tempVideoPath, completedSequence)
      return
    }
    if (handledSequencesRef.current.has(completedSequence)) return
    handledSequencesRef.current.add(completedSequence)
    currentSequenceRef.current += 1

    // WeChat limits one recording to 30 seconds. Start the next segment first.
    startCameraRecording()
    const persistence = persistSegment(
      tempVideoPath,
      completedSequence,
      SEGMENT_DURATION_SECONDS,
    )
    trackPersistence(persistence)
    void persistence.catch(handlePersistenceFailure)
  }

  function startCameraRecording() {
    const cameraContext = cameraContextRef.current ?? Taro.createCameraContext()
    cameraContextRef.current = cameraContext
    segmentStartedAtRef.current = Date.now()
    cameraContext.startRecord({
      success() {
        recordingRef.current = true
        setRecording(true)
        setPreparing(false)
        startRecordingTimer()
      },
      timeoutCallback(result) {
        handleTimedOutSegment(result.tempVideoPath)
      },
      fail(reason) {
        recordingRef.current = false
        setRecording(false)
        setPreparing(false)
        setError(reason.errMsg || '无法开始录像')
      },
    })
  }

  async function beginRecording() {
    setPreparing(true)
    setError('')
    try {
      const created = await createShoulderPressVideoSession(actionId)
      if (!shouldStartRecordingAfterSessionCreated(pageHiddenRef.current)) {
        setPreparing(false)
        return
      }
      const session: ShoulderPressSession = {
        actionId,
        videoId: created.video_id,
        startedAt: Date.now(),
        durationSeconds: 0,
        phase: 'recording',
        segments: [],
      }
      saveShoulderPressSession(Taro, session)
      currentSequenceRef.current = 0
      elapsedRef.current = 0
      handledSequencesRef.current.clear()
      setElapsedSeconds(0)
      startCameraRecording()
    } catch (reason) {
      setPreparing(false)
      setError(reason instanceof Error ? reason.message : '无法创建训练录像会话')
    }
  }

  function startCountdown() {
    if (!cameraAllowed || countdown !== null || recording || preparing) return
    let value = 5
    setError('')
    setCountdown(value)
    countdownTimerRef.current = setInterval(() => {
      value -= 1
      if (value <= 0) {
        if (countdownTimerRef.current) clearInterval(countdownTimerRef.current)
        countdownTimerRef.current = null
        setCountdown(null)
        void beginRecording()
        return
      }
      setCountdown(value)
    }, 1000)
  }

  async function completeRecording(tempVideoPath: string, sequenceIndex: number) {
    const durationSeconds = Math.max(
      1,
      Math.round((Date.now() - segmentStartedAtRef.current) / 1000),
    )
    if (!handledSequencesRef.current.has(sequenceIndex)) {
      handledSequencesRef.current.add(sequenceIndex)
      await persistSegment(tempVideoPath, sequenceIndex, durationSeconds)
    }
    await waitForPendingPersistence([...pendingPersistenceRef.current])
    const session = loadShoulderPressSession(Taro)
    if (!session) throw new Error('训练录像会话已丢失')
    const segmentCount = Math.max(
      sequenceIndex + 1,
      ...session.segments.map((item) => item.sequenceIndex + 1),
    )
    saveShoulderPressSession(Taro, {
      ...session,
      phase: 'uploading',
      segmentCount,
      durationSeconds: Math.max(elapsedRef.current, 1),
      trainingDate: localDate(),
    })
    void queueRunnerRef.current?.drainAvailable()
    if (!pageHiddenRef.current) {
      await Taro.redirectTo({ url: buildShoulderPressUploadUrl() })
    }
  }

  function finalizeCompletedSegment(tempVideoPath: string, sequenceIndex: number): Promise<void> {
    if (finalCompletionRef.current) return finalCompletionRef.current
    if (stopTimeoutRef.current) clearTimeout(stopTimeoutRef.current)
    stopTimeoutRef.current = null
    finalCompletionRef.current = completeRecording(tempVideoPath, sequenceIndex)
      .then(() => {
        setFinishing(false)
      })
      .catch((failure) => {
        finalizingRef.current = false
        setFinishing(false)
        setError(failure instanceof Error ? failure.message : '训练录像收尾失败')
      })
    return finalCompletionRef.current
  }

  function abandonCurrentSegment(message: string) {
    const session = loadShoulderPressSession(Taro)
    if (session) {
      saveShoulderPressSession(Taro, {
        ...session,
        phase: 'uploading',
        segmentCount: Math.max(session.segmentCount ?? 0, currentSequenceRef.current + 1),
        durationSeconds: Math.max(elapsedRef.current, 1),
        trainingDate: localDate(),
        unrecoverableReason: message,
      })
    }
    finalizingRef.current = false
    recordingRef.current = false
    setRecording(false)
    setFinishing(false)
    setError(message)
    if (!pageHiddenRef.current) {
      void Taro.redirectTo({ url: buildShoulderPressUploadUrl() })
    }
  }

  function stopRecording(reason: 'manual' | 'hidden') {
    if (!recordingRef.current || finalizingRef.current) return
    finalizingRef.current = true
    setFinishing(true)
    if (recordingTimerRef.current) clearInterval(recordingTimerRef.current)
    recordingTimerRef.current = null
    const sequenceIndex = currentSequenceRef.current
    stopTimeoutRef.current = setTimeout(() => {
      stopTimeoutRef.current = null
      abandonCurrentSegment('录像文件生成超时，请重新训练')
    }, STOP_RECORD_TIMEOUT_MS)
    const cameraContext = cameraContextRef.current ?? Taro.createCameraContext()
    cameraContext.stopRecord({
      success(result) {
        if (stopTimeoutRef.current) clearTimeout(stopTimeoutRef.current)
        stopTimeoutRef.current = null
        recordingRef.current = false
        setRecording(false)
        void finalizeCompletedSegment(result.tempVideoPath, sequenceIndex)
      },
      fail(failure) {
        if (finalCompletionRef.current) return
        if (shouldWaitForAutomaticFinalSegment(reason)) {
          setError('正在等待系统返回最后一段录像')
          return
        }
        if (stopTimeoutRef.current) clearTimeout(stopTimeoutRef.current)
        stopTimeoutRef.current = null
        abandonCurrentSegment(
          failure.errMsg || `${reason === 'hidden' ? '后台' : '手动'}结束录像失败`,
        )
      },
    })
  }

  const busy = countdown !== null || preparing || recording || finishing
  return (
    <View className='training-camera-page'>
      {cameraAllowed ? (
        <Camera
          className='training-camera-fullscreen'
          devicePosition={cameraPosition}
          mode='normal'
          onError={(event) => setError(event.detail.errMsg || '摄像头不可用')}
        />
      ) : (
        <View className='camera-permission-fullscreen'>
          <Text className='camera-permission-title'>摄像头未授权</Text>
          <Text className='camera-permission-copy'>请允许使用摄像头后开始训练。</Text>
          <Button
            className='camera-permission-button'
            onClick={() => Taro.openSetting().then((setting) => {
              const allowed = Boolean(setting.authSetting['scope.camera'])
              setCameraAllowed(allowed)
              if (allowed) setError('')
            })}
          >
            打开设置
          </Button>
        </View>
      )}

      <View className='camera-top-controls'>
        {!busy ? (
          <Button className='camera-icon-button' onClick={() => Taro.navigateBack()}>
            <Text className='camera-control-icon'>‹</Text>
            <Text className='camera-control-label'>返回</Text>
          </Button>
        ) : <View className='camera-control-spacer' />}
        <View className={`camera-status ${recording ? 'recording' : ''}`}>
          <View className='recording-dot' />
          <Text>{recording ? displayDuration(elapsedSeconds) : preparing ? '正在准备' : '准备就绪'}</Text>
        </View>
        <Button
          className='camera-icon-button'
          disabled={busy || !cameraAllowed}
          onClick={() => setCameraPosition((value) => value === 'front' ? 'back' : 'front')}
        >
          <Text className='camera-control-icon'>↻</Text>
          <Text className='camera-control-label'>切换</Text>
        </Button>
      </View>

      {countdown !== null ? (
        <View className='camera-countdown'>
          <Text className='camera-countdown-number'>{countdown}</Text>
          <Text className='camera-countdown-label'>准备开始</Text>
        </View>
      ) : null}

      {finishing ? (
        <View className='camera-finalizing'>
          <View className='camera-finalizing-spinner' />
          <Text className='camera-finalizing-title'>正在保存最后一段录像</Text>
          <Text className='camera-finalizing-copy'>完成后将自动进入上传页面</Text>
        </View>
      ) : null}

      {error ? <Text className='camera-error'>{error}</Text> : null}

      <View className='camera-bottom-controls'>
        <Text className='camera-guidance'>请保持上半身和双臂完整入镜，训练将持续录制</Text>
        <Button
          className={recording ? 'camera-stop-button' : 'camera-start-button'}
          disabled={!cameraAllowed || countdown !== null || preparing || finishing}
          onClick={recording ? () => stopRecording('manual') : startCountdown}
        >
          {recording ? '结束训练' : '开始训练'}
        </Button>
      </View>
    </View>
  )
}
