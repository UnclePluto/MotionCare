import { Button, Camera, Text, View } from '@tarojs/components'
import Taro, { useDidHide, useDidShow } from '@tarojs/taro'
import { useCallback, useEffect, useRef, useState } from 'react'

import { DEMO_SHOULDER_PRESS_VIDEO_URL } from '../../demo/data'
import { ShoulderPressTrainingOverlay } from './trainingOverlay'

const DEMO_DURATION_SECONDS = 60
const DEMO_DURATION_MS = DEMO_DURATION_SECONDS * 1000

export default function ShoulderPressDemoCameraPage() {
  const [cameraReady, setCameraReady] = useState(false)
  const [started, setStarted] = useState(false)
  const [running, setRunning] = useState(false)
  const [completed, setCompleted] = useState(false)
  const [elapsedMs, setElapsedMs] = useState(0)
  const [error, setError] = useState('')
  const startedAtRef = useRef(0)
  const elapsedBaseRef = useRef(0)
  const startedRef = useRef(false)
  const runningRef = useRef(false)
  const completedRef = useRef(false)
  const pausedByBackgroundRef = useRef(false)

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
          setError('')
        }}
        onError={() => {
          setCameraReady(false)
          setError('请开启摄像头权限，摄像头可用后才能开始训练')
        }}
      />

      <View className='training-camera-safe-top'>
        <View className='training-camera-back' onClick={() => Taro.navigateBack({ delta: 1 })}>
          ‹
        </View>
      </View>

      <ShoulderPressTrainingOverlay
        videoUrl={DEMO_SHOULDER_PRESS_VIDEO_URL}
        elapsedMs={elapsedMs}
        expectedDurationSeconds={DEMO_DURATION_SECONDS}
        started={started}
      />

      {error ? <Text className='camera-error'>{error}</Text> : null}

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
                disabled={!cameraReady}
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
              {error ? (
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
