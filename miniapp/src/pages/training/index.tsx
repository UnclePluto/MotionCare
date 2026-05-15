import { Button, Input, Picker, Text, View } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import { useState } from 'react'

import { request } from '../../api/client'
import { todayLocalDate } from '../../utils/date'

const STATUS_OPTIONS = [
  { label: '已完成', value: 'completed' },
  { label: '部分完成', value: 'partial' },
  { label: '未完成', value: 'missed' }
] as const

export default function TrainingPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const [statusIndex, setStatusIndex] = useState(0)
  const [duration, setDuration] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit() {
    if (!Number.isFinite(actionId)) {
      setError('训练动作无效')
      return
    }
    setLoading(true)
    setError('')
    try {
      await request('/patient-app/training-records/', {
        method: 'POST',
        data: {
          prescription_action: actionId,
          training_date: todayLocalDate(),
          status: STATUS_OPTIONS[statusIndex].value,
          actual_duration_minutes: duration ? Number(duration) : null,
          note
        }
      })
      Taro.navigateBack()
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <View className='page training-page'>
      <Text className='title'>训练记录</Text>
      <View className='field-card'>
        <Text className='label'>完成状态</Text>
        <Picker
          mode='selector'
          range={STATUS_OPTIONS.map((item) => item.label)}
          value={statusIndex}
          onChange={(event) => setStatusIndex(Number(event.detail.value))}
        >
          <Text className='value'>{STATUS_OPTIONS[statusIndex].label}</Text>
        </Picker>
      </View>
      <View className='field-card'>
        <Text className='label'>实际时长</Text>
        <Input
          className='input'
          type='number'
          value={duration}
          placeholder='分钟'
          onInput={(event) => setDuration(event.detail.value)}
        />
      </View>
      <View className='field-card'>
        <Text className='label'>备注</Text>
        <Input
          className='input'
          value={note}
          placeholder='可选'
          onInput={(event) => setNote(event.detail.value)}
        />
      </View>
      {error ? <Text className='error'>{error}</Text> : null}
      <Button className='primary-button' loading={loading} onClick={submit}>
        提交
      </Button>
    </View>
  )
}
