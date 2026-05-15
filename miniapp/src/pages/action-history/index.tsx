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
      <Text className='title'>训练历史</Text>
      {error ? <Text className='error'>{error}</Text> : null}
      {data ? (
        <View>
          <View className='panel'>
            <View className='row'>
              <Text className='label'>近 7 天</Text>
              <Text className='value'>{data.last_7_days_completed_count} 次</Text>
            </View>
            <View className='row'>
              <Text className='label'>近 30 天</Text>
              <Text className='value'>{data.last_30_days_completed_count} 次</Text>
            </View>
          </View>
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
      ) : (
        <Text className='muted'>加载中</Text>
      )}
    </View>
  )
}
