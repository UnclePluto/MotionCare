import { Button, Camera, Text, Video, View } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import { request } from '../../api/client'
import type { CurrentPrescription } from '../../types/patientApp'
import { canStartShoulderPressRecording, resolveShoulderPressAction, type ShoulderPressAction } from './pageState'
import {
  buildPendingShoulderPressUpload,
  buildShoulderPressUploadUrl,
  isUsableTempVideoPath,
  loadPendingShoulderPressUpload,
  savePendingShoulderPressUpload
} from './session'

type CameraContext = ReturnType<typeof Taro.createCameraContext>

function startCameraRecord(
  context: CameraContext,
  onTimeout: (tempVideoPath: string) => void
): Promise<void> {
  return new Promise((resolve, reject) => {
    context.startRecord({
      success: () => resolve(),
      fail: () => reject(new Error('摄像头录像启动失败，请检查权限后重试')),
      timeoutCallback: (result) => onTimeout(result.tempVideoPath)
    })
  })
}

function stopCameraRecord(context: CameraContext): Promise<string> {
  return new Promise((resolve, reject) => {
    context.stopRecord({
      success: (result) => resolve(result.tempVideoPath),
      fail: () => reject(new Error('录像停止失败，请稍后重试'))
    })
  })
}

export default function ShoulderPressPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const [action, setAction] = useState<ShoulderPressAction | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [cameraReady, setCameraReady] = useState(false)
  const [recording, setRecording] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [recordedVideoPath, setRecordedVideoPath] = useState('')
  const [error, setError] = useState('')
  const recordingRef = useRef(false)
  const commandInFlightRef = useRef(false)
  const finalizeInFlightRef = useRef(false)
  const cameraContextRef = useRef<CameraContext | null>(null)

  useEffect(() => {
    const pending = loadPendingShoulderPressUpload(Taro)
    if (pending) {
      Taro.reLaunch({ url: buildShoulderPressUploadUrl() })
      return
    }
    if (!Number.isInteger(actionId) || actionId <= 0) {
      setError('训练动作无效，请返回当前处方重新进入')
      setLoaded(true)
      return
    }

    request<CurrentPrescription>('/patient-app/current-prescription/')
      .then((prescription) => {
        const currentAction = resolveShoulderPressAction(prescription, actionId)
        setAction(currentAction)
        if (!currentAction) {
          setError('动作已失效或处方已更新，请返回当前处方重新进入')
        }
      })
      .catch((loadError) => {
        setError(loadError instanceof Error ? loadError.message : '当前动作加载失败，请稍后重试')
      })
      .finally(() => setLoaded(true))
  }, [actionId])

  async function persistRecordedVideo(tempVideoPath: string) {
    if (finalizeInFlightRef.current) return
    finalizeInFlightRef.current = true
    setProcessing(true)
    setRecording(false)
    recordingRef.current = false
    setError('')

    try {
      if (!isUsableTempVideoPath(tempVideoPath)) {
        throw new Error('录像文件路径无效，请重新录制')
      }
      setRecordedVideoPath(tempVideoPath)
      const videoInfo = await Taro.getVideoInfo({ src: tempVideoPath })
      const pending = buildPendingShoulderPressUpload({
        actionId,
        tempFilePath: tempVideoPath,
        videoInfo: {
          duration: videoInfo.duration,
          size: videoInfo.size
        }
      })
      savePendingShoulderPressUpload(Taro, pending)
      await Taro.reLaunch({ url: buildShoulderPressUploadUrl() })
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : '录像信息读取失败，请重试')
    } finally {
      finalizeInFlightRef.current = false
      setProcessing(false)
    }
  }

  async function startRecording() {
    const canStart = canStartShoulderPressRecording({
      actionReady: action !== null,
      cameraReady,
      busy: commandInFlightRef.current || finalizeInFlightRef.current || recordingRef.current
    })
    if (!canStart) {
      setError(action ? '摄像头尚未就绪，请开启权限后再开始录像' : '当前动作不可用，请返回处方重新进入')
      return
    }

    commandInFlightRef.current = true
    setProcessing(true)
    setError('')
    try {
      const context = cameraContextRef.current ?? Taro.createCameraContext()
      cameraContextRef.current = context
      await startCameraRecord(context, (tempVideoPath) => {
        void persistRecordedVideo(tempVideoPath)
      })
      recordingRef.current = true
      setRecording(true)
      setRecordedVideoPath('')
      try {
        Taro.createVideoContext('shoulder-press-example-video').play()
      } catch {
        // 示例视频仍保留原生控件，自动播放失败不阻塞录像。
      }
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : '摄像头录像启动失败，请检查权限后重试')
    } finally {
      commandInFlightRef.current = false
      setProcessing(false)
    }
  }

  async function stopRecording() {
    if (!recordingRef.current || commandInFlightRef.current || finalizeInFlightRef.current) return

    commandInFlightRef.current = true
    setProcessing(true)
    setError('')
    try {
      const context = cameraContextRef.current ?? Taro.createCameraContext()
      cameraContextRef.current = context
      const tempVideoPath = await stopCameraRecord(context)
      commandInFlightRef.current = false
      await persistRecordedVideo(tempVideoPath)
    } catch (stopError) {
      recordingRef.current = false
      setRecording(false)
      setError(stopError instanceof Error ? stopError.message : '录像停止失败，请稍后重试')
    } finally {
      commandInFlightRef.current = false
      setProcessing(false)
    }
  }

  const canStart = canStartShoulderPressRecording({
    actionReady: action !== null,
    cameraReady,
    busy: processing || recording || Boolean(recordedVideoPath)
  })

  return (
    <View className='page shoulder-press-page'>
      <View className='page-hero shoulder-press-hero'>
        <Text className='eyebrow'>抗阻训练</Text>
        <Text className='title'>{action?.action_name ?? '肩部推举'}</Text>
        <Text className='muted'>保持正面或近正面入镜，跟随示例缓慢完成动作。</Text>
      </View>

      <View className='training-stage'>
        <View className='training-media-slot'>
          <Text className='training-media-label'>我的画面</Text>
          <View className='training-media-frame camera-frame'>
            <Camera
              className='camera-preview'
              devicePosition='front'
              flash='off'
              mode='normal'
              onInitDone={() => {
                setCameraReady(true)
              }}
              onError={() => {
                setCameraReady(false)
                setError('请开启摄像头权限，摄像头可用后才能开始录像')
              }}
            />
          </View>
        </View>
        <View className='training-media-slot'>
          <Text className='training-media-label'>示例动作</Text>
          <View className='training-media-frame example-frame'>
            {action?.video_url ? (
              <Video
                id='shoulder-press-example-video'
                className='example-video'
                src={action.video_url}
                title={action.action_name}
                controls
                loop
                objectFit='contain'
                showFullscreenBtn={false}
                showCenterPlayBtn
                enableProgressGesture
              />
            ) : (
              <View className='example-fallback'>
                <Text className='label'>动作说明</Text>
                <Text className='paragraph'>
                  {action?.action_instruction || '医生暂未配置示例视频，请按动作说明缓慢完成肩部推举。'}
                </Text>
              </View>
            )}
          </View>
        </View>
      </View>

      {!loaded ? <Text className='muted loading-text'>正在加载当前动作</Text> : null}
      {recording ? <Text className='recording-status'>正在录像，示例视频可继续播放和暂停。</Text> : null}
      {processing && recordedVideoPath ? <Text className='recording-status'>正在读取录像时长与文件大小。</Text> : null}
      {error ? <Text className='error'>{error}</Text> : null}

      {!action && loaded ? (
        <Button
          className='secondary-button full-button'
          onClick={() => Taro.reLaunch({ url: '/pages/prescription/index' })}
        >
          返回当前处方
        </Button>
      ) : recordedVideoPath && !recording ? (
        <Button
          className='primary-button full-button'
          loading={processing}
          disabled={processing}
          onClick={() => void persistRecordedVideo(recordedVideoPath)}
        >
          重试读取录像
        </Button>
      ) : recording ? (
        <Button
          className='primary-button full-button'
          loading={processing}
          disabled={processing}
          onClick={() => void stopRecording()}
        >
          完成录像并上传
        </Button>
      ) : (
        <Button
          className='primary-button full-button'
          loading={processing}
          disabled={!canStart}
          onClick={() => void startRecording()}
        >
          开始录像
        </Button>
      )}
    </View>
  )
}
