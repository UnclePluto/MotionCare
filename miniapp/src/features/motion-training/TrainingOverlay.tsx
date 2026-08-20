import { Text, Video, View } from '@tarojs/components'
import { useEffect, useRef, useState } from 'react'

import {
  formatMotionTrainingTimer,
  nextMotionTrainingPreviewVisibility,
  remainingMotionTrainingSeconds,
  type MotionTrainingPreviewVisibility
} from './pageState'

type TouchPoint = { clientX: number; clientY: number }

function touchPointFromEvent(
  event: unknown,
  field: 'touches' | 'changedTouches'
): TouchPoint | undefined {
  return (event as Record<typeof field, TouchPoint[]>)[field][0]
}

export type MotionTrainingOverlayProps = {
  videoUrl: string | null
  elapsedMs: number
  expectedDurationSeconds: number
  started: boolean
  topInset?: number
  onVideoError?: () => Promise<void> | void
}

export function MotionTrainingOverlay(props: MotionTrainingOverlayProps) {
  const [visibility, setVisibility] = useState<MotionTrainingPreviewVisibility>('visible')
  const [videoError, setVideoError] = useState(false)
  const [refreshingVideo, setRefreshingVideo] = useState(false)
  const touchStartRef = useRef<TouchPoint | null>(null)
  const refreshAttemptedRef = useRef(false)
  const previousVideoUrlRef = useRef(props.videoUrl)
  const remainingSeconds = remainingMotionTrainingSeconds(
    props.elapsedMs,
    props.expectedDurationSeconds
  )

  const finishSwipe = (point: TouchPoint) => {
    const start = touchStartRef.current
    touchStartRef.current = null
    if (!start) return
    setVisibility((current) => nextMotionTrainingPreviewVisibility({
      visibility: current,
      deltaX: point.clientX - start.clientX,
      deltaY: point.clientY - start.clientY
    }))
  }

  const startSwipe = (event: unknown) => {
    const point = touchPointFromEvent(event, 'touches')
    if (point) touchStartRef.current = point
  }

  const endSwipe = (event: unknown) => {
    const point = touchPointFromEvent(event, 'changedTouches')
    if (point) finishSwipe(point)
  }

  const hiddenClassName = visibility === 'hidden'
    ? ' shoulder-training-preview-hidden'
    : ''
  const topInset = `${props.topInset ?? 24}px`

  useEffect(() => {
    if (
      props.videoUrl &&
      props.videoUrl !== previousVideoUrlRef.current
    ) {
      setVideoError(false)
      setRefreshingVideo(false)
    }
    previousVideoUrlRef.current = props.videoUrl
  }, [props.videoUrl])

  const handleVideoError = () => {
    setVideoError(true)
    if (refreshAttemptedRef.current || !props.onVideoError) {
      setRefreshingVideo(false)
      return
    }
    refreshAttemptedRef.current = true
    setRefreshingVideo(true)
    void Promise.resolve()
      .then(() => props.onVideoError?.())
      .catch(() => undefined)
      .finally(() => setRefreshingVideo(false))
  }

  return (
    <View className='shoulder-training-overlay'>
      {props.started ? (
        <View className='shoulder-training-timer' style={{ top: topInset }}>
          <View><Text>已训练</Text><Text>{formatMotionTrainingTimer(props.elapsedMs)}</Text></View>
          <View><Text>剩余</Text><Text>{formatMotionTrainingTimer(remainingSeconds * 1000)}</Text></View>
        </View>
      ) : null}
      {props.videoUrl && !videoError ? (
        <Video
          className={`shoulder-training-preview${hiddenClassName}`}
          src={props.videoUrl}
          autoplay
          loop
          muted
          controls={false}
          enableProgressGesture={false}
          objectFit='contain'
          style={{ top: topInset }}
          onError={handleVideoError}
          onTouchStart={visibility === 'visible' ? startSwipe : undefined}
          onTouchEnd={visibility === 'visible' ? endSwipe : undefined}
        />
      ) : null}
      {props.videoUrl && visibility === 'hidden' ? (
        <View
          className='shoulder-training-preview-restore'
          style={{ top: topInset }}
          onTouchStart={(event) => {
            const point = touchPointFromEvent(event, 'touches')
            if (point) touchStartRef.current = point
          }}
          onTouchEnd={(event) => {
            const point = touchPointFromEvent(event, 'changedTouches')
            if (point) finishSwipe(point)
          }}
        >
          <Text>←</Text><Text>向左滑恢复示范</Text>
        </View>
      ) : null}
      {videoError ? (
        <View
          className={`shoulder-training-preview-error${hiddenClassName}`}
          style={{ top: topInset }}
          onTouchStart={visibility === 'visible' ? startSwipe : undefined}
          onTouchEnd={visibility === 'visible' ? endSwipe : undefined}
        >
          <Text>{refreshingVideo
            ? '正在重新获取示范视频…'
            : '示范视频暂时无法播放，录像不受影响'}</Text>
        </View>
      ) : null}
    </View>
  )
}
