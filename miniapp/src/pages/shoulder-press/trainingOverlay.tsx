import { Text, Video, View } from '@tarojs/components'
import { useRef, useState } from 'react'

import {
  formatShoulderPressTimer,
  nextShoulderPressPreviewVisibility,
  remainingShoulderPressSeconds,
  type ShoulderPressPreviewVisibility
} from './pageState'

type TouchPoint = { clientX: number; clientY: number }

function touchPointFromEvent(
  event: unknown,
  field: 'touches' | 'changedTouches'
): TouchPoint | undefined {
  return (event as Record<typeof field, TouchPoint[]>)[field][0]
}

export type ShoulderPressTrainingOverlayProps = {
  videoUrl: string | null
  elapsedMs: number
  expectedDurationSeconds: number
}

export function ShoulderPressTrainingOverlay(props: ShoulderPressTrainingOverlayProps) {
  const [visibility, setVisibility] = useState<ShoulderPressPreviewVisibility>('visible')
  const [videoError, setVideoError] = useState(false)
  const touchStartRef = useRef<TouchPoint | null>(null)
  const remainingSeconds = remainingShoulderPressSeconds(
    props.elapsedMs,
    props.expectedDurationSeconds
  )

  const finishSwipe = (point: TouchPoint) => {
    const start = touchStartRef.current
    touchStartRef.current = null
    if (!start) return
    setVisibility((current) => nextShoulderPressPreviewVisibility({
      visibility: current,
      deltaX: point.clientX - start.clientX,
      deltaY: point.clientY - start.clientY
    }))
  }

  return (
    <View className='shoulder-training-overlay'>
      <View className='shoulder-training-timer'>
        <View><Text>已训练</Text><Text>{formatShoulderPressTimer(props.elapsedMs)}</Text></View>
        <View><Text>剩余</Text><Text>{formatShoulderPressTimer(remainingSeconds * 1000)}</Text></View>
      </View>
      {props.videoUrl && visibility === 'visible' && !videoError ? (
        <Video
          className='shoulder-training-preview'
          src={props.videoUrl}
          autoplay
          loop
          muted
          controls={false}
          objectFit='contain'
          onError={() => setVideoError(true)}
          onTouchStart={(event) => {
            const point = touchPointFromEvent(event, 'touches')
            if (point) touchStartRef.current = point
          }}
          onTouchEnd={(event) => {
            const point = touchPointFromEvent(event, 'changedTouches')
            if (point) finishSwipe(point)
          }}
        />
      ) : null}
      {props.videoUrl && visibility === 'hidden' ? (
        <View
          className='shoulder-training-preview-restore'
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
      {videoError && visibility === 'visible' ? (
        <View
          className='shoulder-training-preview-error'
          onTouchStart={(event) => {
            const point = touchPointFromEvent(event, 'touches')
            if (point) touchStartRef.current = point
          }}
          onTouchEnd={(event) => {
            const point = touchPointFromEvent(event, 'changedTouches')
            if (point) finishSwipe(point)
          }}
        >
          <Text>示范视频暂时无法播放</Text>
        </View>
      ) : null}
    </View>
  )
}
