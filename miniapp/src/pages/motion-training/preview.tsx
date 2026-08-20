import { Button, Text, Video, View } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import { useCallback, useEffect, useRef, useState } from 'react'

import { fetchCurrentPrescriptionData } from '../../demo/patientAppData'
import { isDemoSession } from '../../demo/session'
import {
  reLaunchPendingMotionTrainingUploadIfNeeded,
  resolveMotionTrainingAction,
  type MotionTrainingAction
} from '../../features/motion-training/pageState'
import { buildMotionTrainingCameraUrl } from '../../features/motion-training/session'

function playableVideoUrl(action: MotionTrainingAction | null): string {
  if (!action || action.video_unavailable) return ''
  return action.video_url?.trim() ?? ''
}

export default function MotionTrainingPreviewPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const demoMode = isDemoSession()
  const [action, setAction] = useState<MotionTrainingAction | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [videoError, setVideoError] = useState(false)
  const [refreshingVideo, setRefreshingVideo] = useState(false)
  const [retryKey, setRetryKey] = useState(0)
  const refreshedAfterVideoErrorRef = useRef(false)
  const mountedRef = useRef(true)

  const loadAction = useCallback(async (): Promise<MotionTrainingAction | null> => {
    const prescription = await fetchCurrentPrescriptionData()
    if (!mountedRef.current) return null
    const currentAction = resolveMotionTrainingAction(prescription, actionId)
    setAction(currentAction)
    return currentAction
  }, [actionId])

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
        const currentAction = await loadAction()
        if (!cancelled && !currentAction) {
          setError('动作已失效或运动计划已更新，请返回当前运动计划重新进入')
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
    return () => {
      cancelled = true
      mountedRef.current = false
    }
  }, [actionId, demoMode, loadAction])

  async function handleVideoError() {
    if (refreshedAfterVideoErrorRef.current) {
      setVideoError(true)
      return
    }

    refreshedAfterVideoErrorRef.current = true
    setRefreshingVideo(true)
    try {
      const refreshedAction = await loadAction()
      if (!mountedRef.current) return
      if (!refreshedAction) {
        setAction(null)
        setError('动作已失效或运动计划已更新，请返回当前运动计划重新进入')
        return
      }
      setVideoError(false)
      setRetryKey((value) => value + 1)
    } catch {
      if (mountedRef.current) setVideoError(true)
    } finally {
      if (mountedRef.current) setRefreshingVideo(false)
    }
  }

  const videoUrl = playableVideoUrl(action)
  const showVideo = Boolean(videoUrl) && !videoError
  const videoNotice = action && !showVideo
    ? videoError
      ? '示范视频暂时无法播放，您仍可直接开始训练。'
      : '当前动作暂无可播放的示范视频，您仍可直接开始训练。'
    : ''

  return (
    <View className='page motion-training-preview-page'>
      <View className='motion-training-preview-media'>
        {showVideo ? (
          <Video
            key={retryKey}
            className='motion-training-preview-video'
            src={videoUrl}
            autoplay
            loop
            muted
            controls={false}
            objectFit='contain'
            onError={() => void handleVideoError()}
          />
        ) : null}
        {videoNotice ? (
          <View className='motion-training-preview-error'>
            <Text>{videoNotice}</Text>
          </View>
        ) : null}
        {refreshingVideo ? <Text className='muted'>正在重新获取示范视频</Text> : null}
      </View>
      {!loaded ? <Text className='muted loading-text'>正在加载动作预览</Text> : null}
      {error ? <Text className='error'>{error}</Text> : null}
      {action ? (
        <View className='button-row motion-training-preview-actions'>
          <Button className='secondary-button' onClick={() => Taro.navigateBack()}>
            关闭预览
          </Button>
          <Button
            className='primary-button'
            onClick={() => Taro.redirectTo({ url: buildMotionTrainingCameraUrl(actionId) })}
          >
            开始训练
          </Button>
        </View>
      ) : loaded ? (
        <Button
          className='secondary-button full-button'
          onClick={() => Taro.reLaunch({ url: '/pages/prescription/index' })}
        >
          返回当前运动计划
        </Button>
      ) : null}
    </View>
  )
}
