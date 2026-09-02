import { Button, Text, View } from '@tarojs/components'
import Taro, { useDidHide, useDidShow, useRouter } from '@tarojs/taro'
import { useCallback, useEffect, useRef, useState } from 'react'

import { fetchCurrentPrescriptionData } from '../../demo/patientAppData'
import { isDemoSession } from '../../demo/session'
import {
  createMotionTrainingAudioPlayer,
  type MotionTrainingAudioPlayer
} from '../../features/motion-training/alertAudio'
import { getMotionInstructionAudioSrc } from '../../features/motion-training/instructionAudioManifest'
import {
  reLaunchPendingMotionTrainingUploadIfNeeded,
  resolveMotionTrainingAction,
  type MotionTrainingAction
} from '../../features/motion-training/pageState'
import {
  buildMotionTrainingCameraUrl,
  buildMotionTrainingPreviewUrl
} from '../../features/motion-training/session'

function hasPlayableVideo(action: MotionTrainingAction): boolean {
  return !action.video_unavailable && Boolean(action.video_url?.trim())
}

type InstructionAudioStatus = 'idle' | 'playing' | 'played'

export default function MotionTrainingPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const demoMode = isDemoSession()
  const instructionPlayerRef = useRef<MotionTrainingAudioPlayer | null>(null)
  const pageVisibleRef = useRef(true)
  const visitGenerationRef = useRef(0)
  const loadedActionRef = useRef<{ generation: number; action: MotionTrainingAction } | null>(null)
  const currentSourceKeyRef = useRef<string | null>(null)
  const autoPlayedSourceKeyRef = useRef<string | null>(null)
  const playbackAttemptRef = useRef(0)
  const [action, setAction] = useState<MotionTrainingAction | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [instructionAudioStatus, setInstructionAudioStatus] = useState<InstructionAudioStatus>('idle')
  const [instructionAudioError, setInstructionAudioError] = useState('')

  if (!instructionPlayerRef.current) {
    instructionPlayerRef.current = createMotionTrainingAudioPlayer({ timeoutMs: 90_000 })
  }

  const stopInstruction = useCallback(() => {
    playbackAttemptRef.current += 1
    setInstructionAudioError('')
    setInstructionAudioStatus((status) => status === 'playing' ? 'played' : status)
    try {
      instructionPlayerRef.current?.stop()
    } catch {
      // 停止语音失败不能阻断离页或训练导航。
    }
  }, [])

  const playInstruction = useCallback(async (sourceKey: unknown) => {
    const src = getMotionInstructionAudioSrc(sourceKey)
    if (!src) return

    const attempt = playbackAttemptRef.current + 1
    playbackAttemptRef.current = attempt
    setInstructionAudioError('')
    setInstructionAudioStatus('playing')

    let played = false
    try {
      played = await instructionPlayerRef.current!.play(src)
    } catch {
      played = false
    }

    if (playbackAttemptRef.current !== attempt) return
    setInstructionAudioStatus('played')
    if (!played) {
      setInstructionAudioError('语音播放失败，请阅读文字说明')
    }
  }, [])

  const syncInstructionSource = useCallback((sourceKeyValue: unknown, generation: number) => {
    if (!pageVisibleRef.current || visitGenerationRef.current !== generation) return

    const sourceKey = typeof sourceKeyValue === 'string' ? sourceKeyValue : null
    if (currentSourceKeyRef.current !== sourceKey) {
      if (currentSourceKeyRef.current !== null) {
        stopInstruction()
      }
      currentSourceKeyRef.current = sourceKey
      setInstructionAudioError('')
      setInstructionAudioStatus('idle')
    }

    if (
      !sourceKey
      || !getMotionInstructionAudioSrc(sourceKey)
      || autoPlayedSourceKeyRef.current === sourceKey
    ) {
      return
    }

    autoPlayedSourceKeyRef.current = sourceKey
    void playInstruction(sourceKey)
  }, [playInstruction, stopInstruction])

  useEffect(() => {
    const previousGeneration = visitGenerationRef.current
    const generation = previousGeneration + 1
    visitGenerationRef.current = generation
    if (previousGeneration > 0) {
      stopInstruction()
    }
    loadedActionRef.current = null
    currentSourceKeyRef.current = null
    autoPlayedSourceKeyRef.current = null
    setAction(null)
    setLoaded(false)
    setError('')
    setInstructionAudioError('')
    setInstructionAudioStatus('idle')

    let cancelled = false
    const isCurrentVisit = () => !cancelled && visitGenerationRef.current === generation

    async function bootstrap() {
      if (!demoMode) {
        const redirected = await reLaunchPendingMotionTrainingUploadIfNeeded(Taro)
        if (!isCurrentVisit() || redirected) return
      }

      if (!Number.isInteger(actionId) || actionId <= 0) {
        if (!isCurrentVisit()) return
        setError('训练动作无效，请返回当前运动计划重新进入')
        setLoaded(true)
        return
      }

      try {
        const prescription = await fetchCurrentPrescriptionData()
        if (!isCurrentVisit()) return
        const currentAction = resolveMotionTrainingAction(prescription, actionId)
        setAction(currentAction)
        loadedActionRef.current = currentAction ? { generation, action: currentAction } : null
        syncInstructionSource(currentAction?.source_key, generation)
        if (!currentAction) {
          setError('动作已失效或运动计划已更新，请返回当前运动计划重新进入')
        }
      } catch (loadError) {
        if (isCurrentVisit()) {
          setError(loadError instanceof Error ? loadError.message : '当前动作加载失败，请稍后重试')
        }
      } finally {
        if (isCurrentVisit()) setLoaded(true)
      }
    }

    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [actionId, demoMode, stopInstruction, syncInstructionSource])

  useDidHide(() => {
    pageVisibleRef.current = false
    stopInstruction()
  })

  useDidShow(() => {
    pageVisibleRef.current = true
    const loadedAction = loadedActionRef.current
    if (loadedAction?.generation === visitGenerationRef.current) {
      syncInstructionSource(loadedAction.action.source_key, loadedAction.generation)
    }
  })

  useEffect(() => () => {
    pageVisibleRef.current = false
    visitGenerationRef.current += 1
    playbackAttemptRef.current += 1
    try {
      instructionPlayerRef.current?.dispose()
    } catch {
      // 销毁异常不应影响页面卸载。
    }
  }, [])

  const previewAvailable = action ? hasPlayableVideo(action) : false

  return (
    <View className='page motion-training-guide-page'>
      <View className='page-hero motion-training-guide-hero'>
        <Text className='eyebrow'>{action?.training_type ?? '动作跟练'}</Text>
        <Text className='title'>{action?.action_name ?? '动作跟练'}</Text>
        <Text className='muted'>先熟悉动作要领，准备好后再进入独立摄像训练。</Text>
      </View>

      <View className='motion-training-instruction-section'>
        <Text className='section-title'>训练准备</Text>
        <View className='preparation-row'>
          <Text className='preparation-mark'>1</Text>
          <Text className='paragraph'>将手机竖直固定在身体正前方。</Text>
        </View>
        <View className='preparation-row'>
          <Text className='preparation-mark'>2</Text>
          <Text className='paragraph'>确保训练动作需要的身体部位完整进入画面。</Text>
        </View>
        <View className='preparation-row'>
          <Text className='preparation-mark'>3</Text>
          <Text className='paragraph'>进入摄像页后，等待画面就绪再开始训练。</Text>
        </View>
        {action?.action_instruction ? (
          <Text className='motion-training-action-instruction'>{action.action_instruction}</Text>
        ) : null}
        {action && getMotionInstructionAudioSrc(action.source_key) ? (
          <View className='motion-training-instruction-audio-controls'>
            <Button
              className='secondary-button full-button motion-training-instruction-audio-button'
              disabled={instructionAudioStatus === 'playing'}
              onClick={() => void playInstruction(action.source_key)}
            >
              {instructionAudioStatus === 'playing'
                ? '正在播放说明'
                : instructionAudioStatus === 'played'
                  ? '重新播放说明'
                  : '播放动作说明'}
            </Button>
            {instructionAudioError ? (
              <Text className='motion-training-instruction-audio-error'>
                {instructionAudioError}
              </Text>
            ) : null}
          </View>
        ) : null}
      </View>

      {!loaded ? <Text className='muted loading-text'>正在加载当前动作</Text> : null}
      {error ? <Text className='error'>{error}</Text> : null}

      {!action && loaded ? (
        <Button
          className='secondary-button full-button'
          onClick={() => Taro.reLaunch({ url: '/pages/prescription/index' })}
        >
          返回当前运动计划
        </Button>
      ) : action ? (
        <View className='button-row motion-training-guide-actions'>
          <Button
            className='primary-button'
            onClick={() => {
              stopInstruction()
              Taro.navigateTo({ url: buildMotionTrainingCameraUrl(actionId) })
            }}
          >
            开始训练
          </Button>
          {previewAvailable ? (
            <Button
              className='secondary-button'
              onClick={() => {
                stopInstruction()
                Taro.navigateTo({ url: buildMotionTrainingPreviewUrl(actionId) })
              }}
            >
              动作预览
            </Button>
          ) : null}
        </View>
      ) : null}
    </View>
  )
}
