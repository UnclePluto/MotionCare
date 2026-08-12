import { Button, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import { fetchCurrentPrescriptionData } from '../../demo/patientAppData'
import { isDemoSession } from '../../demo/session'
import type { CurrentPrescription } from '../../types/patientApp'
import {
  loadPendingGameUpload,
  startPendingGameUploadRetryLoop,
  subscribePendingGameUploadRetryLoop,
  tryUploadPendingGameRecord,
} from '../game-session/retryUpload'
import {
  SHOULDER_PRESS_SOURCE_KEY
} from '../shoulder-press/session'
import { reLaunchPendingShoulderPressUploadIfNeeded } from '../shoulder-press/pageState'
import { actionButtonLabel, actionEntryUrl } from './actionRouting'
import {
  readCurrentPrescriptionCache,
  writeCurrentPrescriptionCache
} from './cache'
import { loadGameSessionSubpackage } from './gameSubpackage'

function pendingGameUploadBannerText(): string {
  const pending = loadPendingGameUpload(Taro)
  if (!pending) return ''
  if (pending.retry_paused_until_next_launch) return '有游戏训练结果待补传，已暂停到下次打开后继续。'
  if (pending.next_retry_at > Date.now()) return '有游戏训练结果待补传，稍后将自动重试。'
  return '有游戏训练结果待补传，正在尝试自动补传。'
}

export default function PrescriptionPage() {
  const demoMode = isDemoSession()
  const [data, setData] = useState<CurrentPrescription>(() => (
    demoMode ? null : readCurrentPrescriptionCache() ?? null
  ))
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(() => (
    demoMode ? false : readCurrentPrescriptionCache() !== undefined
  ))
  const [pendingUploadBanner, setPendingUploadBanner] = useState('')
  const [gameLoadingActionId, setGameLoadingActionId] = useState<number | null>(null)
  const [gameLoadProgress, setGameLoadProgress] = useState(0)
  const [gameLoadError, setGameLoadError] = useState('')
  const mountedRef = useRef(true)

  function refreshPendingUploadBanner() {
    setPendingUploadBanner(pendingGameUploadBannerText())
  }

  function loadPrescriptionData() {
    fetchCurrentPrescriptionData()
      .then((body) => {
        if (!demoMode) writeCurrentPrescriptionCache(body)
        if (!mountedRef.current) return
        setData(body)
        setError('')
        setLoaded(true)
      })
      .catch((err) => {
        if (!mountedRef.current) return
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
      await loadGameSessionSubpackage((event) => {
        if (mountedRef.current) setGameLoadProgress(event.progress)
      })
      if (!mountedRef.current) return
      Taro.navigateTo({ url: actionEntryUrl(action) })
    } catch (err) {
      if (!mountedRef.current) return
      setGameLoadError(err instanceof Error ? err.message : '游戏资源加载失败，请稍后重试')
    } finally {
      if (mountedRef.current) setGameLoadingActionId(null)
    }
  }

  useEffect(() => () => {
    mountedRef.current = false
  }, [])

  useEffect(() => {
    if (demoMode) return undefined
    return subscribePendingGameUploadRetryLoop((result) => {
      if (!mountedRef.current) return
      refreshPendingUploadBanner()
      if (result === 'uploaded') {
        loadPrescriptionData()
      }
    })
  }, [demoMode])

  useDidShow(() => {
    setError('')
    setGameLoadError('')
    if (demoMode) {
      setPendingUploadBanner('')
      loadPrescriptionData()
      return
    }
    void reLaunchPendingShoulderPressUploadIfNeeded(Taro).then((redirected) => {
      if (!mountedRef.current) return
      if (redirected) return
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
  })

  if (!loaded) {
    return (
      <View className='page prescription-page'>
        <View className='page-hero'>
          <Text className='eyebrow'>运动安排</Text>
          <Text className='title'>当前运动计划</Text>
        </View>
        {!demoMode && pendingUploadBanner ? <Text className='pending-upload-banner'>{pendingUploadBanner}</Text> : null}
        <Text className='muted loading-text'>正在加载当前运动计划</Text>
      </View>
    )
  }

  if (!data) {
    return (
      <View className='page prescription-page'>
        <View className='page-hero'>
          <Text className='eyebrow'>运动安排</Text>
          <Text className='title'>当前运动计划</Text>
        </View>
        {!demoMode && pendingUploadBanner ? <Text className='pending-upload-banner'>{pendingUploadBanner}</Text> : null}
        {error ? (
          <Text className='error'>{error}</Text>
        ) : (
          <View className='empty-state'>
            <Text className='value'>暂无生效运动计划</Text>
            <Text className='muted'>指导老师开具运动计划后，这里会展示动作、本周目标和训练入口。</Text>
          </View>
        )}
      </View>
    )
  }

  return (
    <View className='page prescription-page'>
      <View className='page-hero prescription-hero'>
        <Text className='eyebrow'>运动安排</Text>
        <Text className='title'>当前运动计划 v{data.version}</Text>
        <Text className='muted'>
          本周：{data.week_start} 至 {data.week_end}
        </Text>
      </View>
      {!demoMode && pendingUploadBanner ? <Text className='pending-upload-banner'>{pendingUploadBanner}</Text> : null}
      {error ? <Text className='muted prescription-refresh-error'>{error}</Text> : null}
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
          <Text className='value'>运动计划暂未配置动作</Text>
          <Text className='muted'>请联系指导老师补充训练动作后再开始训练。</Text>
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
            {!demoMode ? (
              <Text className='muted'>最近：{action.recent_record?.training_date ?? '暂无记录'}</Text>
            ) : null}
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
              {!demoMode ? (
                <Button
                  className='secondary-button'
                  disabled={gameLoadingActionId !== null}
                  onClick={() => Taro.navigateTo({ url: `/pages/action-history/index?actionId=${action.id}` })}
                >
                  查看历史
                </Button>
              ) : null}
            </View>
          </View>
        )
      })}
    </View>
  )
}
