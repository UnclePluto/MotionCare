import { Button, Input, Picker, Text, View } from '@tarojs/components'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { useState } from 'react'

import { request } from '../../api/client'
import type { CurrentPrescription } from '../../types/patientApp'
import { todayLocalDate } from '../../utils/date'

const DIFFICULTY_OPTIONS = ['简单', '中等', '困难']

type NumberParseOptions = {
  message: string
  min?: number
  max?: number
  integer?: boolean
}

type NumberParseResult = { ok: true; value: number | null } | { ok: false; message: string }

function parseOptionalNumber(value: string, options: NumberParseOptions): NumberParseResult {
  const normalized = value.trim()
  if (!normalized) return { ok: true, value: null }

  const parsed = Number(normalized)
  if (!Number.isFinite(parsed)) {
    return { ok: false, message: options.message }
  }
  if (options.integer && !Number.isInteger(parsed)) {
    return { ok: false, message: options.message }
  }
  if (options.min !== undefined && parsed < options.min) {
    return { ok: false, message: options.message }
  }
  if (options.max !== undefined && parsed > options.max) {
    return { ok: false, message: options.message }
  }
  return { ok: true, value: parsed }
}

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
    setPrescription(null)
    request<CurrentPrescription>('/patient-app/current-prescription/')
      .then((body) => {
        setPrescription(body)
        setLoaded(true)
      })
      .catch((err) => {
        setPrescription(null)
        setError(err instanceof Error ? err.message : '加载失败')
        setLoaded(true)
      })
  })

  const action = prescription?.actions.find((item) => item.id === actionId)

  async function submit() {
    if (loading) return
    if (!action || action.internal_type !== 'game') {
      setError('游戏动作无效，请返回当前处方重新进入')
      return
    }

    const parsedDuration = parseOptionalNumber(duration, {
      message: '完成时长必须是非负整数分钟',
      min: 0,
      integer: true
    })
    if (!parsedDuration.ok) {
      setError(parsedDuration.message)
      return
    }

    const parsedScore = parseOptionalNumber(score, {
      message: '得分必须在 0 到 100 之间',
      min: 0,
      max: 100
    })
    if (!parsedScore.ok) {
      setError(parsedScore.message)
      return
    }

    const parsedAccuracyRate = parseOptionalNumber(accuracyRate, {
      message: '正确率必须在 0 到 100 之间',
      min: 0,
      max: 100
    })
    if (!parsedAccuracyRate.ok) {
      setError(parsedAccuracyRate.message)
      return
    }

    const parsedErrorCount = parseOptionalNumber(errorCount, {
      message: '错误次数必须是非负整数',
      min: 0,
      integer: true
    })
    if (!parsedErrorCount.ok) {
      setError(parsedErrorCount.message)
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
          actual_duration_minutes: parsedDuration.value,
          score: parsedScore.value,
          form_data: {
            accuracy_rate: parsedAccuracyRate.value,
            error_count: parsedErrorCount.value,
            difficulty: DIFFICULTY_OPTIONS[difficultyIndex],
            raw_detail: { source: 'miniapp-placeholder' }
          },
          note: note.trim()
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

  if (!prescription) {
    return (
      <View className='page game-session-page'>
        <Text className='title'>游戏训练</Text>
        <Text className='muted'>暂无生效处方</Text>
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
      <Button className='primary-button' loading={loading} disabled={loading} onClick={submit}>
        提交游戏结果
      </Button>
    </View>
  )
}
