import { Button, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useEffect, useState } from 'react'

import { request } from '../../api/client'
import type { HomeData } from '../../types/patientApp'
import {
  loadPendingGameUpload,
  startPendingGameUploadRetryLoop,
  subscribePendingGameUploadRetryLoop,
  tryUploadPendingGameRecord,
} from '../game-session/retryUpload'

function pendingGameUploadBannerText(): string {
  const pending = loadPendingGameUpload(Taro)
  if (!pending) return ''
  if (pending.retry_paused_until_next_launch) return '有游戏训练结果待补传，已暂停到下次打开后继续。'
  if (pending.next_retry_at > Date.now()) return '有游戏训练结果待补传，稍后将自动重试。'
  return '有游戏训练结果待补传，正在尝试自动补传。'
}

export default function HomePage() {
  const [data, setData] = useState<HomeData | null>(null)
  const [error, setError] = useState('')
  const [pendingUploadBanner, setPendingUploadBanner] = useState('')

  function refreshPendingUploadBanner() {
    setPendingUploadBanner(pendingGameUploadBannerText())
  }

  function loadHomeData() {
    request<HomeData>('/patient-app/home/')
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : '加载失败'))
  }

  useEffect(() => {
    return subscribePendingGameUploadRetryLoop((result) => {
      refreshPendingUploadBanner()
      if (result === 'uploaded') {
        loadHomeData()
      }
    })
  }, [])

  useDidShow(() => {
    setError('')
    refreshPendingUploadBanner()
    void tryUploadPendingGameRecord(Taro)
      .then((result) => {
        if (result === 'uploaded') {
          loadHomeData()
        }
      })
      .finally(() => {
        refreshPendingUploadBanner()
        startPendingGameUploadRetryLoop(Taro)
      })
    loadHomeData()
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
      {pendingUploadBanner ? <Text className='pending-upload-banner'>{pendingUploadBanner}</Text> : null}
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
