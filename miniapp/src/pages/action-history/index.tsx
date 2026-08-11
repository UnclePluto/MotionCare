import { Text, View } from '@tarojs/components'
import { useDidShow, useRouter } from '@tarojs/taro'
import { useState } from 'react'

import { request } from '../../api/client'
import type { TrainingRecordSummary } from '../../types/patientApp'

type History = {
  prescription_action: number
  last_7_days_completed_count: number
  last_30_days_completed_count: number
  records: TrainingRecordSummary[]
}

const STATUS_LABEL: Record<TrainingRecordSummary['status'], string> = {
  completed: '已完成',
  partial: '部分完成',
  missed: '未完成'
}

export default function ActionHistoryPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const [data, setData] = useState<History | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')

  useDidShow(() => {
    setLoaded(false)
    setData(null)
    if (!Number.isFinite(actionId)) {
      setError('训练动作无效')
      setLoaded(true)
      return
    }
    setError('')
    request<History>(`/patient-app/actions/${actionId}/history/`)
      .then((body) => {
        setData(body)
        setLoaded(true)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : '加载失败')
        setLoaded(true)
      })
  })

  return (
    <View className='page action-history-page'>
      <View className='page-hero'>
        <Text className='eyebrow'>训练回顾</Text>
        <Text className='title'>训练历史</Text>
        <Text className='muted'>查看近期完成情况。</Text>
      </View>
      {error ? <Text className='error'>{error}</Text> : null}
      {data ? (
        <View className='history-content'>
          <View className='stat-grid history-stats'>
            <View className='stat-card'>
              <Text className='label'>近 7 天</Text>
              <Text className='value'>{data.last_7_days_completed_count} 次</Text>
            </View>
            <View className='stat-card'>
              <Text className='label'>近 30 天</Text>
              <Text className='value'>{data.last_30_days_completed_count} 次</Text>
            </View>
          </View>
          <View className='history-list'>
            {data.records.length === 0 ? (
              <View className='empty-state'>
                <Text className='value'>暂无训练记录</Text>
                <Text className='muted'>完成本动作后，最近记录会显示在这里。</Text>
              </View>
            ) : (
              data.records.map((record) => (
                <View key={record.id} className='history-row'>
                  <Text className='value'>
                    {record.training_date} · {STATUS_LABEL[record.status]}
                  </Text>
                  <Text className='muted'>{record.actual_duration_minutes ?? '-'} 分钟</Text>
                  {record.note ? <Text className='muted'>{record.note}</Text> : null}
                </View>
              ))
            )}
          </View>
        </View>
      ) : loaded ? (
        <View className='state-card'>
          <Text className='value'>训练历史暂时无法加载</Text>
          <Text className='muted'>请稍后从运动计划页重新进入。</Text>
        </View>
      ) : (
        <Text className='muted loading-text'>正在加载训练历史</Text>
      )}
    </View>
  )
}
