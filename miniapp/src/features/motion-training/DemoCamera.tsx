import { Button, Camera, Text, View } from '@tarojs/components'
import Taro, { useDidHide, useDidShow, useRouter } from '@tarojs/taro'
import { useCallback, useEffect, useRef, useState } from 'react'

import { fetchCurrentPrescriptionData } from '../../demo/patientAppData'
import {
  resolveMotionTrainingAction,
  type MotionTrainingAction
} from './pageState'
import { MotionTrainingOverlay } from './TrainingOverlay'

const DEMO_DURATION_SECONDS = 600
const DEMO_DURATION_MS = DEMO_DURATION_SECONDS * 1000

export default function DemoCamera() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const [action, setAction] = useState<MotionTrainingAction | null>(null)
  const [cameraReady, setCameraReady] = useState(false)
  const [started, setStarted] = useState(false)
  const [running, setRunning] = useState(false)
  const [completed, setCompleted] = useState(false)
  const [elapsedMs, setElapsedMs] = useState(0)
  const [loadError, setLoadError] = useState('')
  const [cameraError, setCameraError] = useState('')
  const startedAtRef = useRef(0)
  const elapsedBaseRef = useRef(0)
  const startedRef = useRef(false)
  const runningRef = useRef(false)
  const completedRef = useRef(false)
  const pausedByBackgroundRef = useRef(false)

  useEffect(() => {
    let cancelled = false

    async function loadAction() {
      if (!Number.isInteger(actionId) || actionId <= 0) {
        setLoadError('训练动作无效，请返回当前运动计划重新进入')
        return
      }
      try {
        const prescription = await fetchCurrentPrescriptionData()
        if (cancelled) return
        const currentAction = resolveMotionTrainingAction(prescription, actionId)
        setAction(currentAction)
        if (!currentAction) {
          setLoadError('动作已失效或运动计划已更新，请返回当前运动计划重新进入')
        }
      } catch (error) {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : '当前动作加载失败，请稍后重试')
        }
      }
    }

    void loadAction()
    return () => {
      cancelled = true
    }
  }, [actionId])

  const currentElapsedMs = useCallback(() => Math.min(
    DEMO_DURATION_MS,
    elapsedBaseRef.current + (
      runningRef.current ? Math.max(0, Date.now() - startedAtRef.current) : 0
    )
  ), [])

  const finishTraining = useCallback((nextElapsedMs = currentElapsedMs()) => {
    const clampedElapsedMs = Math.min(DEMO_DURATION_MS, nextElapsedMs)
    elapsedBaseRef.current = clampedElapsedMs
    runningRef.current = false
    completedRef.current = true
    pausedByBackgroundRef.current = false
    setElapsedMs(clampedElapsedMs)
    setRunning(false)
    setCompleted(true)
  }, [currentElapsedMs])

  useEffect(() => {
    if (!running) return undefined

    const timer = setInterval(() => {
      const nextElapsedMs = currentElapsedMs()
      setElapsedMs(nextElapsedMs)
      if (nextElapsedMs >= DEMO_DURATION_MS) {
        finishTraining(DEMO_DURATION_MS)
      }
    }, 1000)

    return () => clearInterval(timer)
  }, [currentElapsedMs, finishTraining, running])

  useDidHide(() => {
    if (!runningRef.current || completedRef.current) return
    const nextElapsedMs = currentElapsedMs()
    elapsedBaseRef.current = nextElapsedMs
    runningRef.current = false
    pausedByBackgroundRef.current = true
    setElapsedMs(nextElapsedMs)
    setRunning(false)
  })

  useDidShow(() => {
    if (
      !pausedByBackgroundRef.current ||
      !startedRef.current ||
      completedRef.current
    ) return
    pausedByBackgroundRef.current = false
    startedAtRef.current = Date.now()
    runningRef.current = true
    setRunning(true)
  })

  return (
    <View className='training-camera-page'>
      <Camera
        className='training-camera-fullscreen'
        devicePosition='front'
        flash='off'
        mode='normal'
        onInitDone={() => {
          setCameraReady(true)
          setCameraError('')
        }}
        onError={() => {
          setCameraReady(false)
          setCameraError('请开启摄像头权限，摄像头可用后才能开始训练')
        }}
      />

      <View className='training-camera-safe-top'>
        <View className='training-camera-back' onClick={() => Taro.navigateBack({ delta: 1 })}>
          ‹
        </View>
      </View>

      <MotionTrainingOverlay
        videoUrl={action?.video_url ?? ''}
        elapsedMs={elapsedMs}
        expectedDurationSeconds={DEMO_DURATION_SECONDS}
        started={started}
      />

      {loadError || cameraError ? (
        <Text className='camera-error'>{cameraError || loadError}</Text>
      ) : null}

      {completed ? (
        <View className='training-preflight-overlay'>
          <Text className='training-preflight-message'>体验完成</Text>
          <Text className='camera-permission-copy'>本次演示不保存训练记录或摄像内容。</Text>
          <Button
            className='camera-start-button'
            onClick={() => Taro.redirectTo({ url: '/pages/prescription/index' })}
          >
            返回运动计划
          </Button>
        </View>
      ) : (
        <View className='training-camera-bottom-action'>
          {started ? (
            <Button
              className='camera-stop-button'
              onClick={() => finishTraining()}
            >
              提前结束
            </Button>
          ) : (
            <>
              <Button
                className='camera-start-button'
                disabled={!cameraReady || !action}
                onClick={() => {
                  elapsedBaseRef.current = 0
                  startedAtRef.current = Date.now()
                  startedRef.current = true
                  runningRef.current = true
                  setStarted(true)
                  setRunning(true)
                }}
              >
                开始训练
              </Button>
              {cameraError ? (
                <Button
                  className='training-secondary-button'
                  onClick={() => void Taro.openSetting()}
                >
                  打开设置
                </Button>
              ) : null}
            </>
          )}
        </View>
      )}
    </View>
  )
}
