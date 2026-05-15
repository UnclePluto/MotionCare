import { Button, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'

import { request } from '../../api/client'
import type { CurrentPrescription } from '../../types/patientApp'

export default function PrescriptionPage() {
  const [data, setData] = useState<CurrentPrescription>(null)
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(false)

  useDidShow(() => {
    setError('')
    request<CurrentPrescription>('/patient-app/current-prescription/')
      .then((body) => {
        setData(body)
        setLoaded(true)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : '加载失败')
        setLoaded(true)
      })
  })

  if (!loaded) {
    return (
      <View className='page prescription-page'>
        <Text className='title'>当前处方</Text>
        <Text className='muted'>加载中</Text>
      </View>
    )
  }

  if (!data) {
    return (
      <View className='page prescription-page'>
        <Text className='title'>当前处方</Text>
        {error ? <Text className='error'>{error}</Text> : <Text className='muted'>暂无生效处方</Text>}
      </View>
    )
  }

  return (
    <View className='page prescription-page'>
      <Text className='title'>当前处方 v{data.version}</Text>
      <Text className='muted'>
        本周：{data.week_start} 至 {data.week_end}
      </Text>
      {data.actions.map((action) => (
        <View key={action.id} className='action-card'>
          <Text className='value'>{action.action_name}</Text>
          <Text className='muted'>{action.action_type}</Text>
          <View className='row'>
            <Text className='label'>本周进度</Text>
            <Text className='value'>
              {action.weekly_completed_count}/{action.weekly_target_count} 次
            </Text>
          </View>
          <Text className='muted'>最近：{action.recent_record?.training_date ?? '暂无记录'}</Text>
          <View className='button-row'>
            <Button
              className='primary-button'
              onClick={() => Taro.navigateTo({ url: `/pages/training/index?actionId=${action.id}` })}
            >
              开始训练
            </Button>
            <Button
              className='secondary-button'
              onClick={() => Taro.navigateTo({ url: `/pages/action-history/index?actionId=${action.id}` })}
            >
              训练历史
            </Button>
          </View>
        </View>
      ))}
    </View>
  )
}
