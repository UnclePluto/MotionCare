import { Button, Text, Video, View } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import { useEffect, useState } from 'react'

import { request } from '../../api/client'
import type { CurrentPrescription } from '../../types/patientApp'
import {
  reLaunchPendingShoulderPressUploadIfNeeded,
  resolveShoulderPressAction,
  type ShoulderPressAction
} from './pageState'
import { buildShoulderPressCameraUrl } from './session'

export default function ShoulderPressPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const [action, setAction] = useState<ShoulderPressAction | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [videoError, setVideoError] = useState(false)

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

      <View className='follow-video-section'>
        <Text className='section-title'>示例动作</Text>
        {action?.video_url && !videoError ? (
          <Video
            className='follow-video'
            src={action.video_url}
            title={action.action_name}
            controls
            objectFit='contain'
            showFullscreenBtn
            onError={() => setVideoError(true)}
          />
        ) : (
          <View className='example-fallback guide-video-fallback'>
            <Text className='label'>动作说明</Text>
            <Text className='paragraph'>
              {action?.action_instruction || '医生暂未配置可播放的示例视频，请按动作说明缓慢完成肩部推举。'}
            </Text>
          </View>
        )}
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
      {videoError ? (
        <Text className='pending-upload-banner'>示例视频暂时无法播放，仍可按动作说明完成训练。</Text>
      ) : null}
      {error ? <Text className='error'>{error}</Text> : null}

      {!action && loaded ? (
        <Button
          className='secondary-button full-button'
          onClick={() => Taro.reLaunch({ url: '/pages/prescription/index' })}
        >
          返回当前处方
        </Button>
      ) : (
        <Button
          className='primary-button full-button shoulder-guide-start'
          disabled={!action}
          onClick={() => Taro.navigateTo({ url: buildShoulderPressCameraUrl(actionId) })}
        >
          进入摄像训练
        </Button>
      )}
    </View>
  )
}
