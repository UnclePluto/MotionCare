import { Button, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import { request } from '../../api/client'
import type { HomeData } from '../../types/patientApp'
import {
  loadPendingGameUpload,
  startPendingGameUploadRetryLoop,
  subscribePendingGameUploadRetryLoop,
  tryUploadPendingGameRecord,
} from '../game-session/retryUpload'
import { reLaunchPendingShoulderPressUploadIfNeeded } from '../shoulder-press/pageState'
import { HOME_ACTIONS, type HomeActionContext } from './homeActions'

function pendingGameUploadBannerText(): string {
  const pending = loadPendingGameUpload(Taro)
  if (!pending) return ''
  if (pending.retry_paused_until_next_launch) return '有游戏训练结果待补传，已暂停到下次打开后继续。'
  if (pending.next_retry_at > Date.now()) return '有游戏训练结果待补传，稍后将自动重试。'
  return '有游戏训练结果待补传，正在尝试自动补传。'
}

export default function HomePage() {
  const [data, setData] = useState<HomeData | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [pendingUploadBanner, setPendingUploadBanner] = useState('')
  const mountedRef = useRef(true)

  function refreshPendingUploadBanner() {
    setPendingUploadBanner(pendingGameUploadBannerText())
  }

  function loadHomeData() {
    request<HomeData>('/patient-app/home/')
      .then((body) => {
        if (!mountedRef.current) return
        setData(body)
        setLoaded(true)
      })
      .catch((err) => {
        if (!mountedRef.current) return
        setError(err instanceof Error ? err.message : '加载失败')
        setLoaded(true)
      })
  }

  useEffect(() => () => {
    mountedRef.current = false
  }, [])

  useEffect(() => {
    return subscribePendingGameUploadRetryLoop((result) => {
      if (!mountedRef.current) return
      refreshPendingUploadBanner()
      if (result === 'uploaded') {
        loadHomeData()
      }
    })
  }, [])

  useDidShow(() => {
    setError('')
    setLoaded(false)
    setData(null)
    void reLaunchPendingShoulderPressUploadIfNeeded(Taro).then((redirected) => {
      if (!mountedRef.current) return
      if (redirected) return
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
  })

  const currentPrescription = data?.current_prescription
  const prescriptionActions = currentPrescription?.actions ?? []
  const firstAction = prescriptionActions[0]
  const completed = prescriptionActions.reduce(
    (sum, action) => sum + action.weekly_completed_count,
    0
  )
  const target = prescriptionActions.reduce(
    (sum, action) => sum + action.weekly_target_count,
    0
  )
  const actionContext: HomeActionContext | null = firstAction
    ? {
        actionId: firstAction.id,
        internalType: firstAction.internal_type,
        sourceKey: firstAction.source_key,
      }
    : null

  return (
    <View className='page home-page'>
      <View className='page-hero home-hero'>
        <Text className='eyebrow'>MotionCare</Text>
        <Text className='title'>今日康复</Text>
        <Text className='muted'>按处方完成训练，查看本周进度与历史记录。</Text>
      </View>
      {pendingUploadBanner ? <Text className='pending-upload-banner'>{pendingUploadBanner}</Text> : null}
      {error ? <Text className='error'>{error}</Text> : null}
      {data ? (
        <View className='home-content'>
          <View className='panel profile-panel'>
            <Text className='label'>当前账户</Text>
            <Text className='value profile-name'>{data.patient.name}</Text>
            <Text className='muted project-name'>{data.project.name}</Text>
          </View>
          <View className='stat-grid'>
            <View className='stat-card'>
              <Text className='label'>本周训练</Text>
              <Text className='value'>
                {currentPrescription ? `${completed}/${target} 次` : '暂无处方'}
              </Text>
            </View>
          </View>
          <View className='action-stack'>
            {HOME_ACTIONS.map((action) => {
              if (action.requiresAction && !actionContext) return null
              return (
                <Button
                  key={action.key}
                  className={action.className}
                  onClick={() => Taro.navigateTo({ url: action.url(actionContext) })}
                >
                  {action.label(actionContext)}
                </Button>
              )
            })}
            {!currentPrescription ? (
              <View className='empty-state full-button'>
                <Text className='value'>暂无生效处方</Text>
                <Text className='muted'>医生开具处方后，这里会显示训练入口和本周进度。</Text>
              </View>
            ) : null}
          </View>
        </View>
      ) : loaded ? (
        <View className='state-card'>
          <Text className='value'>首页暂时无法加载</Text>
          <Text className='muted'>请稍后返回重试，或联系医生确认绑定状态。</Text>
        </View>
      ) : (
        <Text className='muted loading-text'>正在加载今日康复安排</Text>
      )}
    </View>
  )
}
