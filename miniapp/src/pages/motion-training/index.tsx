import { Button, Text, View } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import { useEffect, useState } from 'react'

import { fetchCurrentPrescriptionData } from '../../demo/patientAppData'
import { isDemoSession } from '../../demo/session'
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

export default function MotionTrainingPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const demoMode = isDemoSession()
  const [action, setAction] = useState<MotionTrainingAction | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      if (!demoMode) {
        const redirected = await reLaunchPendingMotionTrainingUploadIfNeeded(Taro)
        if (cancelled || redirected) return
      }

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
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : '当前动作加载失败，请稍后重试')
        }
      } finally {
        if (!cancelled) setLoaded(true)
      }
    }

    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [actionId, demoMode])

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
            onClick={() => Taro.navigateTo({ url: buildMotionTrainingCameraUrl(actionId) })}
          >
            开始训练
          </Button>
          {previewAvailable ? (
            <Button
              className='secondary-button'
              onClick={() => Taro.navigateTo({ url: buildMotionTrainingPreviewUrl(actionId) })}
            >
              动作预览
            </Button>
          ) : null}
        </View>
      ) : null}
    </View>
  )
}
