import { Button, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useRef, useState } from 'react'

import {
  completeShoulderPressUpload,
  createShoulderPressUploadIntent,
  uploadVideoToQiniu
} from './api'
import { uploadStageStates, type UploadStageState } from './pageState'
import {
  clearPendingShoulderPressUpload,
  hasShoulderPressUploadIntent,
  loadPendingShoulderPressUpload,
  savePendingShoulderPressUpload,
  type PendingShoulderPressUpload
} from './session'
import {
  runShoulderPressUploadWorkflow,
  shoulderPressUploadErrorMessage,
  type ShoulderPressUploadPhase
} from './workflow'

const STAGE_LABELS = ['申请凭证', '上传视频', '保存训练记录'] as const

function stageStatusText(state: UploadStageState): string {
  if (state === 'done') return '已完成'
  if (state === 'active') return '进行中'
  return '等待中'
}

export default function ShoulderPressUploadPage() {
  const [pending, setPending] = useState<PendingShoulderPressUpload | null>(() => (
    loadPendingShoulderPressUpload(Taro)
  ))
  const [activePhase, setActivePhase] = useState<ShoulderPressUploadPhase | null>(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [running, setRunning] = useState(false)
  const [missing, setMissing] = useState(pending === null)
  const [error, setError] = useState('')
  const runningRef = useRef(false)

  async function upload() {
    if (runningRef.current) return
    runningRef.current = true
    setRunning(true)
    setMissing(false)
    setError('')

    const currentPending = loadPendingShoulderPressUpload(Taro)
    if (!currentPending) {
      setPending(null)
      setMissing(true)
      setActivePhase(null)
      runningRef.current = false
      setRunning(false)
      return
    }
    setPending(currentPending)

    try {
      await runShoulderPressUploadWorkflow(currentPending, {
        now: () => Date.now(),
        createIntent: createShoulderPressUploadIntent,
        uploadVideo: uploadVideoToQiniu,
        completeUpload: completeShoulderPressUpload,
        savePending: (nextPending) => {
          savePendingShoulderPressUpload(Taro, nextPending)
          setPending(nextPending)
        }
      }, (event) => {
        setActivePhase(event.phase)
        if (event.phase === 'upload') setUploadProgress(event.progress)
      })

      clearPendingShoulderPressUpload(Taro)
      await Taro.reLaunch({ url: '/pages/prescription/index' })
    } catch (uploadError) {
      setPending(loadPendingShoulderPressUpload(Taro))
      setActivePhase(null)
      setError(shoulderPressUploadErrorMessage(uploadError))
    } finally {
      runningRef.current = false
      setRunning(false)
    }
  }

  useDidShow(() => {
    void upload()
  })

  const hasIntent = pending ? hasShoulderPressUploadIntent(pending) : false
  const hasHash = Boolean(pending?.hash)
  const stageStates = uploadStageStates({ hasIntent, hasHash, activePhase })

  if (missing) {
    return (
      <View className='page shoulder-press-upload-page upload-invalid-page'>
        <View className='page-hero'>
          <Text className='eyebrow'>录像信息失效</Text>
          <Text className='title'>无法继续上传</Text>
          <Text className='muted'>本地录像信息缺失或损坏，请保持当前页面并联系医护人员协助处理。</Text>
        </View>
      </View>
    )
  }

  return (
    <View className='page shoulder-press-upload-page'>
      <View className='page-hero upload-hero'>
        <Text className='eyebrow'>训练上传</Text>
        <Text className='title'>请保持小程序打开</Text>
        <Text className='muted'>视频和训练记录保存完成后，将自动返回当前处方。</Text>
      </View>

      <View className='upload-progress-panel'>
        {STAGE_LABELS.map((label, index) => (
          <View key={label} className={`upload-stage upload-stage-${stageStates[index]}`}>
            <Text className='upload-stage-label'>{label}</Text>
            <Text className='upload-stage-status'>{stageStatusText(stageStates[index])}</Text>
          </View>
        ))}
        <View className='upload-meter'>
          <View className='row'>
            <Text className='label'>视频上传进度</Text>
            <Text className='value'>{hasHash ? 100 : uploadProgress}%</Text>
          </View>
          <View className='progress-track'>
            <View className='progress-fill' style={{ width: `${hasHash ? 100 : uploadProgress}%` }} />
          </View>
        </View>
      </View>

      <Text className='upload-lock-note'>上传期间请保持小程序打开。</Text>
      {error ? <Text className='error'>{error}</Text> : null}
      {error ? (
        <Button
          className='primary-button full-button'
          loading={running}
          disabled={running}
          onClick={() => void upload()}
        >
          重试上传
        </Button>
      ) : (
        <Text className='muted upload-running-text'>正在自动处理，请稍候。</Text>
      )}
    </View>
  )
}
