import { Button, Input, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'

import { request } from '../../api/client'
import type { DailyHealth } from '../../types/patientApp'

function maybeNumber(value: string): number | null {
  return value ? Number(value) : null
}

export default function DailyHealthPage() {
  const [steps, setSteps] = useState('')
  const [exerciseMinutes, setExerciseMinutes] = useState('')
  const [sleepHours, setSleepHours] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useDidShow(() => {
    setError('')
    request<DailyHealth | null>('/patient-app/daily-health/today/')
      .then((data) => {
        if (!data) return
        setSteps(data.steps ? String(data.steps) : '')
        setExerciseMinutes(data.exercise_minutes ? String(data.exercise_minutes) : '')
        setSleepHours(data.sleep_hours ?? '')
        setNote(data.note ?? '')
      })
      .catch((err) => setError(err instanceof Error ? err.message : '加载失败'))
  })

  async function submit() {
    setLoading(true)
    setError('')
    try {
      await request('/patient-app/daily-health/today/', {
        method: 'PUT',
        data: {
          steps: maybeNumber(steps),
          exercise_minutes: maybeNumber(exerciseMinutes),
          sleep_hours: sleepHours || null,
          note
        }
      })
      Taro.navigateBack()
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <View className='page daily-health-page'>
      <Text className='title'>今日健康数据</Text>
      <View className='field-card'>
        <Text className='label'>步数</Text>
        <Input className='input' type='number' value={steps} onInput={(event) => setSteps(event.detail.value)} />
      </View>
      <View className='field-card'>
        <Text className='label'>运动时长</Text>
        <Input
          className='input'
          type='number'
          value={exerciseMinutes}
          placeholder='分钟'
          onInput={(event) => setExerciseMinutes(event.detail.value)}
        />
      </View>
      <View className='field-card'>
        <Text className='label'>睡眠时长</Text>
        <Input
          className='input'
          type='digit'
          value={sleepHours}
          placeholder='小时'
          onInput={(event) => setSleepHours(event.detail.value)}
        />
      </View>
      <View className='field-card'>
        <Text className='label'>备注</Text>
        <Input className='input' value={note} onInput={(event) => setNote(event.detail.value)} />
      </View>
      {error ? <Text className='error'>{error}</Text> : null}
      <Button className='primary-button' loading={loading} onClick={submit}>
        保存
      </Button>
    </View>
  )
}
