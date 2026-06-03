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
  const [error, setError] = useState('')

  useDidShow(() => {
    if (!Number.isFinite(actionId)) {
      setError('训练动作无效')
      return
    }
    setError('')
    request<History>(`/patient-app/actions/${actionId}/history/`)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : '加载失败'))
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
            {data.records.map((record) => (
              <View key={record.id} className='history-row'>
                <Text className='value'>
                  {record.training_date} · {STATUS_LABEL[record.status]}
                </Text>
                <Text className='muted'>{record.actual_duration_minutes ?? '-'} 分钟</Text>
                {record.note ? <Text className='muted'>{record.note}</Text> : null}
              </View>
            ))}
          </View>
        </View>
      ) : (
        <Text className='muted loading-text'>加载中</Text>
      )}
    </View>
  )
}
