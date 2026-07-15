import { Button, Text, Video, View } from '@tarojs/components'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { useEffect, useState } from 'react'

import { request } from '../../api/client'
import type { CurrentPrescription } from '../../types/patientApp'
import {
  buildShoulderPressCameraUrl,
  buildShoulderPressUploadUrl,
  loadShoulderPressSession,
} from './session'

type PrescriptionAction = NonNullable<CurrentPrescription>['actions'][number]

export default function ShoulderPressPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const [action, setAction] = useState<PrescriptionAction | null>(null)
  const [error, setError] = useState('')

  useDidShow(() => {
    if (loadShoulderPressSession(Taro)) {
      Taro.redirectTo({ url: buildShoulderPressUploadUrl() })
    }
  })

  useEffect(() => {
    request<CurrentPrescription>('/patient-app/current-prescription/')
      .then((prescription) => {
        const current = prescription?.actions.find((item) => item.id === actionId) ?? null
        setAction(current)
        if (!current) setError('当前处方中未找到该动作，请返回处方页刷新')
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : '动作加载失败'))
  }, [actionId])

  return (
    <View className='page shoulder-guide-page'>
      <View className='page-hero shoulder-guide-hero'>
        <Text className='eyebrow'>动作讲解</Text>
        <Text className='title'>{action?.action_name ?? '肩部推举'}</Text>
        <Text className='muted'>先熟悉动作要领，准备好后再进入摄像训练。</Text>
      </View>

      {action?.video_url ? (
        <View className='follow-video-section'>
          <Text className='section-title'>动作示范</Text>
          <Video className='follow-video' src={action.video_url} controls showFullscreenBtn />
        </View>
      ) : (
        <View className='state-card'>
          <Text className='value'>暂无示范视频</Text>
          <Text className='muted'>请按照下方动作说明完成训练。</Text>
        </View>
      )}

      <View className='shoulder-instruction-section'>
        <Text className='section-title'>训练准备</Text>
        <View className='preparation-row'>
          <Text className='preparation-mark'>1</Text>
          <Text className='paragraph'>将手机竖直固定在身体正前方。</Text>
        </View>
        <View className='preparation-row'>
          <Text className='preparation-mark'>2</Text>
          <Text className='paragraph'>确保上半身、双臂和哑铃完整入镜。</Text>
        </View>
        <View className='preparation-row'>
          <Text className='preparation-mark'>3</Text>
          <Text className='paragraph'>训练期间保持手机稳定，结束后等待视频上传。</Text>
        </View>
        {action?.action_instruction ? (
          <Text className='shoulder-action-instruction'>{action.action_instruction}</Text>
        ) : null}
      </View>

      {error ? <Text className='error'>{error}</Text> : null}
      <Button
        className='primary-button full-button shoulder-guide-start'
        disabled={!action}
        onClick={() => Taro.navigateTo({ url: buildShoulderPressCameraUrl(actionId) })}
      >
        开始训练
      </Button>
    </View>
  )
}
