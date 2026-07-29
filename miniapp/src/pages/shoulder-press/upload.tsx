import { Button, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import {
  finishShoulderPressVideoSession,
  getShoulderPressVideoSession,
  uploadShoulderPressSegment,
} from './api'
import { SegmentQueueRunner } from './segmentQueue'
import {
  clearShoulderPressSession,
  loadShoulderPressSession,
} from './session'
import { runShoulderPressUploadFlow } from './uploadFlow'
import {
  formatBytes,
  formatTransferSpeed,
  getSessionTotalBytes,
} from './uploadMetrics'

type PageStage = 'uploading' | 'processing' | 'done' | 'expired' | 'waiting'

const PROCESSING_LABEL: Record<string, string> = {
  queued: '视频等待处理',
  validating_segments: '正在校验视频分片',
  merging: '正在合并完整视频',
  verifying_merge: '正在校验完整视频',
  uploading_qiniu: '正在保存完整视频',
  verifying_qiniu: '正在确认视频保存结果',
  cleaning: '正在完成训练记录',
  processing_failed: '视频处理正在自动重试',
  failed: '视频处理正在自动重试',
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}

function removeSavedFile(filePath: string): Promise<void> {
  return new Promise((resolve, reject) => {
    Taro.getFileSystemManager().unlink({
      filePath,
      success: () => resolve(),
      fail: (reason) => {
        if (reason.errMsg?.includes('no such file')) resolve()
        else reject(new Error(reason.errMsg || '删除本地视频分片失败'))
      },
    })
  })
}

export default function ShoulderPressUploadPage() {
  const stored = loadShoulderPressSession(Taro)
  const [stage, setStage] = useState<PageStage>('uploading')
  const [progress, setProgress] = useState(0)
  const [stageText, setStageText] = useState('正在准备上传视频分片')
  const [segmentText, setSegmentText] = useState('')
  const [uploadedBytes, setUploadedBytes] = useState(stored?.uploadedBytes ?? 0)
  const [totalBytes, setTotalBytes] = useState(stored ? getSessionTotalBytes(stored) : 0)
  const [bytesPerSecond, setBytesPerSecond] = useState(0)
  const [lastMeasuredSpeed, setLastMeasuredSpeed] = useState(0)
  const [error, setError] = useState('')
  const duration = stored?.durationSeconds ?? 0
  const cancelledRef = useRef(false)
  const runnerRef = useRef<SegmentQueueRunner | null>(null)
  const lastProgressAtRef = useRef(0)

  if (!runnerRef.current) {
    runnerRef.current = new SegmentQueueRunner({
      storage: Taro,
      upload: ({ videoId, segment, onProgress }) => uploadShoulderPressSegment({
        videoId,
        sequenceIndex: segment.sequenceIndex,
        durationSeconds: segment.durationSeconds,
        filePath: segment.savedFilePath,
        onProgress,
      }),
      removeFile: removeSavedFile,
      onProgress: ({
        sequenceIndex,
        progress: segmentProgress,
        uploadedBytes: currentUploadedBytes,
        totalBytes: currentTotalBytes,
        bytesPerSecond: currentBytesPerSecond,
      }) => {
        const session = loadShoulderPressSession(Taro)
        const segmentCount = session?.segmentCount ?? 0
        if (!session || segmentCount <= 0) return
        const now = Date.now()
        const uploadProgress = currentTotalBytes > 0
          ? Math.round((currentUploadedBytes / currentTotalBytes) * 60)
          : 0
        lastProgressAtRef.current = now
        setUploadedBytes(currentUploadedBytes)
        setTotalBytes(currentTotalBytes)
        setBytesPerSecond(currentBytesPerSecond)
        if (currentBytesPerSecond > 0) setLastMeasuredSpeed(currentBytesPerSecond)
        setStage('uploading')
        setStageText('正在上传训练视频')
        setSegmentText(
          `分片 ${Math.min(sequenceIndex + 1, segmentCount)}/${segmentCount} · ${segmentProgress}%`,
        )
        setProgress(Math.min(60, uploadProgress))
      },
    })
  }

  useEffect(() => {
    cancelledRef.current = false
    const speedTimer = setInterval(() => {
      if (
        lastProgressAtRef.current > 0
        && Date.now() - lastProgressAtRef.current > 2_500
      ) {
        setBytesPerSecond(0)
      }
    }, 1_000)
    async function runUntilComplete() {
      while (!cancelledRef.current) {
        try {
          setError('')
          const result = await runShoulderPressUploadFlow({
            storage: Taro,
            drainSegments: () => runnerRef.current!.drainAvailable(),
            finish: finishShoulderPressVideoSession,
            getStatus: getShoulderPressVideoSession,
            sleep,
            isCancelled: () => cancelledRef.current,
            onUpdate(update) {
              setProgress(update.progressPercent)
              setUploadedBytes(update.uploadedBytes)
              setTotalBytes(update.totalBytes)
              if (update.stage === 'uploading') {
                setStage('uploading')
                setStageText('正在上传训练视频')
                setSegmentText(`分片 ${update.uploadedSegmentCount}/${update.segmentCount}`)
              } else {
                setBytesPerSecond(0)
                setStage('processing')
                setStageText(
                  PROCESSING_LABEL[update.processingStatus ?? ''] ?? '视频正在自动处理',
                )
                setSegmentText('视频已上传，后台正在自动完成保存')
              }
            },
          })
          if (result === 'succeeded') {
            setProgress(100)
            setStage('done')
            return
          }
          if (result === 'expired') {
            setStage('expired')
            setError('视频处理未能在 48 小时内完成，请重新训练')
            return
          }
          if (result === 'unrecoverable') {
            setStage('expired')
            setError(loadShoulderPressSession(Taro)?.unrecoverableReason || '录像分片保存失败，请重新训练')
            return
          }
        } catch (reason) {
          setStage('waiting')
          setError(reason instanceof Error ? reason.message : '网络连接异常，正在自动重试')
          await sleep(2_000)
        }
      }
    }
    void runUntilComplete()
    return () => {
      cancelledRef.current = true
      clearInterval(speedTimer)
    }
  }, [])

  if (stage === 'done') {
    return (
      <View className='page shoulder-upload-page shoulder-complete-page'>
        <View className='training-complete-mark'>✓</View>
        <Text className='training-complete-title'>训练结束</Text>
        <Text className='training-complete-copy'>完整训练视频和训练记录已保存。</Text>
        <View className='training-complete-summary'>
          <Text className='label'>本次训练时长</Text>
          <Text className='value'>{duration} 秒</Text>
        </View>
        <Button
          className='primary-button full-button training-complete-button'
          onClick={() => Taro.reLaunch({ url: '/pages/prescription/index' })}
        >
          确认并返回处方
        </Button>
      </View>
    )
  }

  const displayTitle = stage === 'waiting' ? '网络连接中断' : stageText
  return (
    <View className='page shoulder-upload-page'>
      <View className='page-hero'>
        <Text className='eyebrow'>训练保存</Text>
        <Text className='title'>{stage === 'expired' ? '训练视频未保存' : displayTitle}</Text>
        <Text className='muted'>系统会自动完成上传和处理，请保持网络连接。</Text>
      </View>

      <View className='upload-progress-summary'>
        <Text className='upload-progress-value'>{progress}%</Text>
        <Text className='muted'>{segmentText || displayTitle}</Text>
        <View className='progress-track'>
          <View className='progress-fill' style={{ width: `${progress}%` }} />
        </View>
        <View className='upload-transfer-metrics'>
          <View className='upload-transfer-metric'>
            <Text className='label'>已上传</Text>
            <Text className='value'>
              {formatBytes(uploadedBytes)} / {formatBytes(totalBytes)}
            </Text>
          </View>
          <View className='upload-transfer-metric'>
            <Text className='label'>
              {stage === 'processing' ? '最近上传速度' : '传输速度'}
            </Text>
            <Text className='value'>
              {stage === 'processing'
                ? lastMeasuredSpeed > 0
                  ? formatTransferSpeed(lastMeasuredSpeed)
                  : '上传已完成'
                : lastProgressAtRef.current === 0
                  ? '等待传输'
                  : formatTransferSpeed(bytesPerSecond)}
            </Text>
          </View>
        </View>
      </View>

      <View className='upload-steps'>
        {['上传视频分片', '合并并保存完整视频', '生成训练记录'].map((label, index) => {
          const current = stage === 'uploading' || stage === 'waiting' ? 0 : 1
          const complete = index < current
          return (
            <View className='upload-step' key={label}>
              <Text className={`upload-step-mark ${complete ? 'complete' : index === current ? 'active' : ''}`}>
                {complete ? '✓' : index + 1}
              </Text>
              <Text className='value'>{label}</Text>
            </View>
          )
        })}
        <Text className='muted'>录像时长：{duration} 秒</Text>
      </View>

      {error ? <Text className='error'>{error}</Text> : null}
      {stage === 'expired' ? (
        <Button
          className='primary-button full-button'
          onClick={() => {
            clearShoulderPressSession(Taro)
            void Taro.reLaunch({ url: '/pages/prescription/index' })
          }}
        >
          返回处方
        </Button>
      ) : null}
    </View>
  )
}
