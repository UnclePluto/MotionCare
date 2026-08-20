import { Button, Text, Video, View } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import { useEffect, useState } from 'react'

import { fetchCurrentPrescriptionData } from '../../demo/patientAppData'
import { isDemoSession } from '../../demo/session'
import {
  reLaunchPendingShoulderPressUploadIfNeeded,
  resolveShoulderPressAction,
  type ShoulderPressAction
} from './pageState'
import { buildShoulderPressCameraUrl } from './session'

export default function ShoulderPressPreviewPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const demoMode = isDemoSession()
  const [action, setAction] = useState<ShoulderPressAction | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [videoError, setVideoError] = useState(false)
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      if (!demoMode) {
        const redirected = await reLaunchPendingShoulderPressUploadIfNeeded(Taro)
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
        const currentAction = resolveShoulderPressAction(prescription, actionId)
        if (!currentAction?.video_url) {
          setError('当前动作暂无可播放的示范视频，请返回当前运动计划')
        } else {
          setAction(currentAction)
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : '动作预览加载失败，请稍后重试')
        }
      } finally {
        if (!cancelled) setLoaded(true)
      }
    }
    void bootstrap()
    return () => { cancelled = true }
  }, [actionId, demoMode])

  return (
    <View className='page shoulder-preview-page'>
      <View className='shoulder-preview-media'>
        {action?.video_url && !videoError ? (
          <Video
            key={retryKey}
            className='shoulder-preview-video'
            src={action.video_url}
            autoplay
            loop
            muted
            controls={false}
            objectFit='contain'
            onError={() => setVideoError(true)}
          />
        ) : null}
        {videoError ? (
          <View className='shoulder-preview-error'>
            <Text>视频加载失败</Text>
            <Button
              className='secondary-button'
              onClick={() => {
                setVideoError(false)
                setRetryKey((value) => value + 1)
              }}
            >
              重新加载
            </Button>
          </View>
        ) : null}
      </View>
      {!loaded ? <Text className='muted loading-text'>正在加载动作预览</Text> : null}
      {error ? <Text className='error'>{error}</Text> : null}
      {action?.video_url ? (
        <View className='button-row shoulder-preview-actions'>
          <Button className='secondary-button' onClick={() => Taro.navigateBack()}>
            关闭预览
          </Button>
          <Button
            className='primary-button'
            onClick={() => Taro.redirectTo({ url: buildShoulderPressCameraUrl(actionId) })}
          >
            开始训练
          </Button>
        </View>
      ) : (
        <Button
          className='secondary-button full-button'
          onClick={() => Taro.reLaunch({ url: '/pages/prescription/index' })}
        >
          返回当前运动计划
        </Button>
      )}
    </View>
  )
}
