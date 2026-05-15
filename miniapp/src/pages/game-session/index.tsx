import { Button, Input, Picker, Text, View } from '@tarojs/components'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { useState } from 'react'

import { request } from '../../api/client'
import type { CurrentPrescription } from '../../types/patientApp'
import { todayLocalDate } from '../../utils/date'

const DIFFICULTY_OPTIONS = ['简单', '中等', '困难']

export default function GameSessionPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const [prescription, setPrescription] = useState<CurrentPrescription>(null)
  const [loaded, setLoaded] = useState(false)
  const [difficultyIndex, setDifficultyIndex] = useState(0)
  const [duration, setDuration] = useState('')
  const [score, setScore] = useState('')
  const [accuracyRate, setAccuracyRate] = useState('')
  const [errorCount, setErrorCount] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useDidShow(() => {
    setError('')
    setLoaded(false)
    request<CurrentPrescription>('/patient-app/current-prescription/')
      .then((body) => {
        setPrescription(body)
        setLoaded(true)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : '加载失败')
        setLoaded(true)
      })
  })

  const action = prescription?.actions.find((item) => item.id === actionId)

  async function submit() {
    if (!action || action.internal_type !== 'game') {
      setError('游戏动作无效，请返回当前处方重新进入')
      return
    }
    setLoading(true)
    setError('')
    try {
      await request('/patient-app/training-records/', {
        method: 'POST',
        data: {
          prescription_action: action.id,
          training_date: todayLocalDate(),
          status: 'completed',
          actual_duration_minutes: duration ? Number(duration) : null,
          score: score || null,
          form_data: {
            accuracy_rate: accuracyRate ? Number(accuracyRate) : null,
            error_count: errorCount ? Number(errorCount) : null,
            difficulty: DIFFICULTY_OPTIONS[difficultyIndex],
            raw_detail: { source: 'miniapp-placeholder' }
          },
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

  if (!loaded) {
    return (
      <View className='page game-session-page'>
        <Text className='title'>游戏训练</Text>
        <Text className='muted'>加载中</Text>
      </View>
    )
  }

  if (!prescription && error) {
    return (
      <View className='page game-session-page'>
        <Text className='title'>游戏训练</Text>
        <Text className='error'>{error}</Text>
      </View>
    )
  }

  if (!action || action.internal_type !== 'game') {
    return (
      <View className='page game-session-page'>
        <Text className='title'>游戏训练</Text>
        <Text className='error'>游戏动作无效，请返回当前处方重新进入</Text>
      </View>
    )
  }

  return (
    <View className='page game-session-page'>
      <Text className='title'>{action.action_name}</Text>
      <Text className='muted'>动作类型：{action.action_type}</Text>
      <Text className='paragraph'>{action.action_instruction}</Text>
      <View className='panel'>
        <View className='row'>
          <Text className='label'>本周进度</Text>
          <Text className='value'>
            {action.weekly_completed_count}/{action.weekly_target_count} 次
          </Text>
        </View>
        <View className='row'>
          <Text className='label'>建议时长</Text>
          <Text className='value'>{action.duration_minutes ?? '-'} 分钟</Text>
        </View>
      </View>
      <View className='field-card'>
        <Text className='label'>难度</Text>
        <Picker
          mode='selector'
          range={DIFFICULTY_OPTIONS}
          value={difficultyIndex}
          onChange={(event) => setDifficultyIndex(Number(event.detail.value))}
        >
          <Text className='value'>{DIFFICULTY_OPTIONS[difficultyIndex]}</Text>
        </Picker>
      </View>
      <View className='field-card'>
        <Text className='label'>完成时长</Text>
        <Input
          className='input'
          type='number'
          value={duration}
          placeholder='分钟'
          onInput={(event) => setDuration(event.detail.value)}
        />
      </View>
      <View className='field-card'>
        <Text className='label'>得分</Text>
        <Input
          className='input'
          type='digit'
          value={score}
          placeholder='0-100'
          onInput={(event) => setScore(event.detail.value)}
        />
      </View>
      <View className='field-card'>
        <Text className='label'>正确率</Text>
        <Input
          className='input'
          type='digit'
          value={accuracyRate}
          placeholder='0-100'
          onInput={(event) => setAccuracyRate(event.detail.value)}
        />
      </View>
      <View className='field-card'>
        <Text className='label'>错误次数</Text>
        <Input
          className='input'
          type='number'
          value={errorCount}
          placeholder='0'
          onInput={(event) => setErrorCount(event.detail.value)}
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
        提交游戏结果
      </Button>
    </View>
  )
}
