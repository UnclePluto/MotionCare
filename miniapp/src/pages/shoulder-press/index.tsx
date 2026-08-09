import { Button, Text, View } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import { useEffect, useState } from 'react'

import { request } from '../../api/client'
import type { CurrentPrescription } from '../../types/patientApp'
import {
  reLaunchPendingShoulderPressUploadIfNeeded,
  resolveShoulderPressAction,
  type ShoulderPressAction
} from './pageState'
import {
  buildShoulderPressCameraUrl,
  buildShoulderPressPreviewUrl
} from './session'

export default function ShoulderPressPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const [action, setAction] = useState<ShoulderPressAction | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')

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
  }, [actionId])

  return (
    <View className='page shoulder-guide-page'>
      <View className='page-hero shoulder-guide-hero'>
        <Text className='eyebrow'>抗阻训练</Text>
        <Text className='title'>{action?.action_name ?? '肩部推举'}</Text>
        <Text className='muted'>先熟悉动作要领，准备好后再进入独立摄像训练。</Text>
      </View>

      <View className='shoulder-instruction-section'>
        <Text className='section-title'>训练准备</Text>
        <View className='preparation-row'>
          <Text className='preparation-mark'>1</Text>
          <Text className='paragraph'>将手机竖直固定在身体正前方。</Text>
        </View>
        <View className='preparation-row'>
          <Text className='preparation-mark'>2</Text>
          <Text className='paragraph'>确保上半身和双臂完整进入画面。</Text>
        </View>
        <View className='preparation-row'>
          <Text className='preparation-mark'>3</Text>
          <Text className='paragraph'>进入摄像页后，等待画面就绪再开始训练。</Text>
        </View>
      </View>

      {!loaded ? <Text className='muted loading-text'>正在加载当前动作</Text> : null}
      {error ? <Text className='error'>{error}</Text> : null}

      {!action && loaded ? (
        <Button
          className='secondary-button full-button'
          onClick={() => Taro.reLaunch({ url: '/pages/prescription/index' })}
        >
          返回当前处方
        </Button>
      ) : action ? (
        <View className='button-row shoulder-guide-actions'>
          <Button
            className='primary-button'
            onClick={() => Taro.navigateTo({ url: buildShoulderPressCameraUrl(actionId) })}
          >
            开始训练
          </Button>
          {action.video_url ? (
            <Button
              className='secondary-button'
              onClick={() => Taro.navigateTo({ url: buildShoulderPressPreviewUrl(actionId) })}
            >
              动作预览
            </Button>
          ) : null}
        </View>
      ) : null}
    </View>
  )
}
