import { Button, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useEffect, useState } from 'react'

import { request } from '../../api/client'
import type { CurrentPrescription } from '../../types/patientApp'
import {
  loadPendingGameUpload,
  startPendingGameUploadRetryLoop,
  subscribePendingGameUploadRetryLoop,
  tryUploadPendingGameRecord,
} from '../game-session/retryUpload'
import {
  buildShoulderPressUploadUrl,
  loadPendingShoulderPressUpload,
  SHOULDER_PRESS_SOURCE_KEY
} from '../shoulder-press/session'
import { actionButtonLabel, actionEntryUrl } from './actionRouting'
import { loadGameSessionSubpackage } from './gameSubpackage'

function pendingGameUploadBannerText(): string {
  const pending = loadPendingGameUpload(Taro)
  if (!pending) return ''
  if (pending.retry_paused_until_next_launch) return '有游戏训练结果待补传，已暂停到下次打开后继续。'
  if (pending.next_retry_at > Date.now()) return '有游戏训练结果待补传，稍后将自动重试。'
  return '有游戏训练结果待补传，正在尝试自动补传。'
}

export default function PrescriptionPage() {
  const [data, setData] = useState<CurrentPrescription>(null)
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [pendingUploadBanner, setPendingUploadBanner] = useState('')
  const [gameLoadingActionId, setGameLoadingActionId] = useState<number | null>(null)
  const [gameLoadProgress, setGameLoadProgress] = useState(0)
  const [gameLoadError, setGameLoadError] = useState('')

  function refreshPendingUploadBanner() {
    setPendingUploadBanner(pendingGameUploadBannerText())
  }

  function loadPrescriptionData() {
    request<CurrentPrescription>('/patient-app/current-prescription/')
      .then((body) => {
        setData(body)
        setLoaded(true)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : '加载失败')
        setLoaded(true)
      })
  }

  async function startAction(action: NonNullable<CurrentPrescription>['actions'][number]) {
    setGameLoadError('')
    if (action.internal_type !== 'game' || action.source_key === SHOULDER_PRESS_SOURCE_KEY) {
      Taro.navigateTo({ url: actionEntryUrl(action) })
      return
    }
    if (gameLoadingActionId !== null) return

    setGameLoadingActionId(action.id)
    setGameLoadProgress(0)
    try {
      await loadGameSessionSubpackage((event) => setGameLoadProgress(event.progress))
      Taro.navigateTo({ url: actionEntryUrl(action) })
    } catch (err) {
      setGameLoadError(err instanceof Error ? err.message : '游戏资源加载失败，请稍后重试')
    } finally {
      setGameLoadingActionId(null)
    }
  }

  useEffect(() => {
    return subscribePendingGameUploadRetryLoop((result) => {
      refreshPendingUploadBanner()
      if (result === 'uploaded') {
        loadPrescriptionData()
      }
    })
  }, [])

  useDidShow(() => {
    if (loadPendingShoulderPressUpload(Taro)) {
      Taro.reLaunch({ url: buildShoulderPressUploadUrl() })
      return
    }
    setError('')
    setLoaded(false)
    setData(null)
    setGameLoadError('')
    refreshPendingUploadBanner()
    void tryUploadPendingGameRecord(Taro)
      .then((result) => {
        if (result === 'uploaded') {
          loadPrescriptionData()
        }
      })
      .finally(() => {
        refreshPendingUploadBanner()
        startPendingGameUploadRetryLoop(Taro)
      })
    loadPrescriptionData()
  })

  if (!loaded) {
    return (
      <View className='page prescription-page'>
        <View className='page-hero'>
          <Text className='eyebrow'>康复安排</Text>
          <Text className='title'>当前处方</Text>
        </View>
        {pendingUploadBanner ? <Text className='pending-upload-banner'>{pendingUploadBanner}</Text> : null}
        <Text className='muted loading-text'>正在加载当前处方</Text>
      </View>
    )
  }

  if (!data) {
    return (
      <View className='page prescription-page'>
        <View className='page-hero'>
          <Text className='eyebrow'>康复安排</Text>
          <Text className='title'>当前处方</Text>
        </View>
        {pendingUploadBanner ? <Text className='pending-upload-banner'>{pendingUploadBanner}</Text> : null}
        {error ? (
          <Text className='error'>{error}</Text>
        ) : (
          <View className='empty-state'>
            <Text className='value'>暂无生效处方</Text>
            <Text className='muted'>医生开具处方后，这里会展示动作、本周目标和训练入口。</Text>
          </View>
        )}
      </View>
    )
  }

  return (
    <View className='page prescription-page'>
      <View className='page-hero prescription-hero'>
        <Text className='eyebrow'>康复安排</Text>
        <Text className='title'>当前处方 v{data.version}</Text>
        <Text className='muted'>
          本周：{data.week_start} 至 {data.week_end}
        </Text>
      </View>
      {pendingUploadBanner ? <Text className='pending-upload-banner'>{pendingUploadBanner}</Text> : null}
      {gameLoadError ? <Text className='error'>{gameLoadError}</Text> : null}
      {gameLoadingActionId !== null ? (
        <View className='subpackage-loader'>
          <View className='row'>
            <Text className='label'>正在加载游戏资源</Text>
            <Text className='value'>{gameLoadProgress}%</Text>
          </View>
          <View className='progress-track'>
            <View className='progress-fill' style={{ width: `${gameLoadProgress}%` }} />
          </View>
        </View>
      ) : null}
      {data.actions.length === 0 ? (
        <View className='empty-state'>
          <Text className='value'>处方暂未配置动作</Text>
          <Text className='muted'>请联系医生补充训练动作后再开始训练。</Text>
        </View>
      ) : null}
      {data.actions.map((action) => {
        const progressPercent = action.weekly_target_count > 0
          ? Math.min(100, Math.round((action.weekly_completed_count / action.weekly_target_count) * 100))
          : 0

        return (
          <View key={action.id} className='action-card prescription-action-card'>
            <View className='row action-card-header'>
              <View>
                <Text className='value action-title'>{action.action_name}</Text>
                <Text className='muted'>{action.action_type}</Text>
              </View>
              <Text className={`pill ${action.internal_type === 'game' ? 'pill-game' : 'pill-training'}`}>
                {action.internal_type === 'game' ? '游戏' : '训练'}
              </Text>
            </View>
            <View className='action-progress'>
              <View className='row'>
                <Text className='label'>本周进度</Text>
                <Text className='value'>
                  {action.weekly_completed_count}/{action.weekly_target_count} 次
                </Text>
              </View>
              <View className='progress-track mini-progress-track'>
                <View className='progress-fill' style={{ width: `${progressPercent}%` }} />
              </View>
            </View>
            <Text className='muted'>最近：{action.recent_record?.training_date ?? '暂无记录'}</Text>
            <View className='button-row'>
              <Button
                className='primary-button'
                loading={gameLoadingActionId === action.id}
                disabled={gameLoadingActionId !== null}
                onClick={() => {
                  void startAction(action)
                }}
              >
                {actionButtonLabel(action)}
              </Button>
              <Button
                className='secondary-button'
                disabled={gameLoadingActionId !== null}
                onClick={() => Taro.navigateTo({ url: `/pages/action-history/index?actionId=${action.id}` })}
              >
                查看历史
              </Button>
            </View>
          </View>
        )
      })}
    </View>
  )
}
