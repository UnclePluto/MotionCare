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
  started: boolean
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

  return (
    <View className='shoulder-training-overlay'>
      {props.started ? (
        <View className='shoulder-training-timer'>
          <View><Text>已训练</Text><Text>{formatShoulderPressTimer(props.elapsedMs)}</Text></View>
          <View><Text>剩余</Text><Text>{formatShoulderPressTimer(remainingSeconds * 1000)}</Text></View>
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
          onError={() => setVideoError(true)}
          onTouchStart={visibility === 'visible' ? startSwipe : undefined}
          onTouchEnd={visibility === 'visible' ? endSwipe : undefined}
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
      {videoError ? (
        <View
          className={`shoulder-training-preview-error${hiddenClassName}`}
          onTouchStart={visibility === 'visible' ? startSwipe : undefined}
          onTouchEnd={visibility === 'visible' ? endSwipe : undefined}
        >
          <Text>示范视频暂时无法播放</Text>
        </View>
      ) : null}
    </View>
  )
}
