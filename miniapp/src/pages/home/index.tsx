import { Button, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'

import { request } from '../../api/client'
import type { HomeData } from '../../types/patientApp'

export default function HomePage() {
  const [data, setData] = useState<HomeData | null>(null)
  const [error, setError] = useState('')

  useDidShow(() => {
    setError('')
    request<HomeData>('/patient-app/home/')
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : '加载失败'))
  })

  const firstAction = data?.current_prescription?.actions[0]
  const completed = data?.current_prescription?.actions.reduce(
    (sum, action) => sum + action.weekly_completed_count,
    0
  )
  const target = data?.current_prescription?.actions.reduce(
    (sum, action) => sum + action.weekly_target_count,
    0
  )

  return (
    <View className='page home-page'>
      <Text className='title'>今日工作台</Text>
      {error ? <Text className='error'>{error}</Text> : null}
      {data ? (
        <View>
          <View className='panel'>
            <Text className='value'>{data.patient.name}</Text>
            <Text className='muted'>{data.project.name}</Text>
          </View>
          <View className='panel'>
            <View className='row'>
              <Text className='label'>本周训练</Text>
              <Text className='value'>
                {completed ?? 0}/{target ?? 0} 次
              </Text>
            </View>
            <View className='row'>
              <Text className='label'>健康数据</Text>
              <Text className='value'>{data.has_daily_health_today ? '已填写' : '待填写'}</Text>
            </View>
          </View>
          <View className='button-row'>
            <Button
              className='primary-button'
              onClick={() => Taro.navigateTo({ url: '/pages/prescription/index' })}
            >
              当前处方
            </Button>
            <Button
              className='secondary-button'
              onClick={() => Taro.navigateTo({ url: '/pages/daily-health/index' })}
            >
              健康填报
            </Button>
          </View>
          {firstAction ? (
            <Button
              className='primary-button'
              onClick={() => Taro.navigateTo({ url: `/pages/training/index?actionId=${firstAction.id}` })}
            >
              继续训练
            </Button>
          ) : null}
        </View>
      ) : (
        <Text className='muted'>加载中</Text>
      )}
    </View>
  )
}
