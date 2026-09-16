import { Button, Camera, Text, Video, View } from '@tarojs/components'
import Taro, { useDidHide, useDidShow } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'
import { fetchCurrentPrescriptionData, fetchPatientHomeData } from '../../demo/patientAppData'
import { getPatientAppToken } from '../../auth/token'
import type { MotionTrainingAction } from './pageState'
import { MotionTrainingRecorder } from './recorder'
import { createClientSessionId } from './session'
import { createRestAudio } from './restAudio'
import {
  checkCountedStorage, completedAttempts, countedSessions, discardIncomplete, newCountedSession,
  removeCountedFile, shanghaiDate, storeCountedSession, syncCountedQueue, updateCountedSession,
  type CountedAttempt, type CountedSession
} from './countedSession'

export default function CountedCamera({ action, demo }: { action: MotionTrainingAction; demo: boolean }) {
  const [session, setSession] = useState<CountedSession | null>(null)
  const current = useRef<CountedSession | null>(null)
  const [ready, setReady] = useState(demo)
  const [cameraReady, setCameraReady] = useState(demo)
  const [recording, setRecording] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [error, setError] = useState('')
  const [audioError, setAudioError] = useState(false)
  const audio = useRef<ReturnType<typeof createRestAudio> | null>(null)
  if (!audio.current) audio.current = createRestAudio(() => setAudioError(true))
  const [now, setNow] = useState(Date.now())
  const busy = useRef(false)
  const active = useRef<CountedAttempt | null>(null)
  const recorder = useRef<MotionTrainingRecorder | null>(null)
  const visible = useRef(true)
  const mounted = useRef(true)
  const token = useRef(getPatientAppToken())
  const owner = useRef(0)
  const saveChain = useRef(Promise.resolve())
  const pendingEnd = useRef<string | null>(null)
  const interrupting = useRef(false)
  const total = action.sets || 3
  const isOwned = () => demo || token.current === getPatientAppToken()
  const publish = (next: CountedSession) => { current.current = next; if (mounted.current) setSession(next) }
  const persist = (next: CountedSession) => { if (!demo) storeCountedSession(next); publish(next) }
  const refresh = () => {
    if (!demo && current.current && isOwned()) {
      const latest = countedSessions(owner.current).find(s => s.id === current.current!.id)
      if (latest) publish(latest)
    }
  }
  const retry = async () => {
    if (demo || !owner.current || !isOwned()) return
    try { await syncCountedQueue(owner.current); if (mounted.current) refresh() }
    catch (err) { if (mounted.current) setError(err instanceof Error ? err.message : '待上传录像读取失败') }
  }

  useEffect(() => {
    mounted.current = true
    if (demo) { owner.current = 0; setReady(true) } else {
      void fetchPatientHomeData().then(async home => {
        if (!mounted.current || !isOwned()) return
        if (!Number.isInteger(home.project_patient_id) || home.project_patient_id <= 0) throw new Error('当前账号身份无效，请重新登录')
        owner.current = home.project_patient_id
        const old = [...countedSessions(owner.current)].reverse().find(s => s.actionId === action.id && (
          (s.trainingDate === shanghaiDate() && completedAttempts(s).length < s.plannedSets) ||
          (completedAttempts(s).length === s.plannedSets && completedAttempts(s).some(a => !a.uploaded))
        ))
        if (old) {
          const recovered = await discardIncomplete(old)
          if (!mounted.current) return
          publish(recovered)
          const done = completedAttempts(recovered)
          if (done.length && done.length < total) audio.current?.restore(Date.parse(done[done.length - 1].endedAt!) + 180000)
          if (old.attempts.some(a => !a.completed && !a.abandoned)) setError('上次录像已中断，请重做本组。已完成组已保留。')
        }
        setReady(true); void retry()
      }).catch(err => { if (mounted.current) setError(err instanceof Error ? err.message : '运动进度读取失败，请返回重试') })
    }
    const timer = setInterval(() => { if (mounted.current) { setNow(Date.now()); audio.current?.update() } }, 250)
    const uploadTimer = demo ? undefined : setInterval(() => { if (visible.current) void retry() }, 15000)
    return () => {
      mounted.current = false; visible.current = false; audio.current?.dispose()
      clearInterval(timer); if (uploadTimer) clearInterval(uploadTimer)
      if (active.current && !pendingEnd.current) void abandon('录像已中断，请重做本组')
    }
  }, [])

  async function abandon(message: string) {
    const attempt = active.current
    if (!attempt) return
    interrupting.current = true
    const abandonedRecorder = recorder.current
    recorder.current = null
    active.current = null; pendingEnd.current = null
    if (mounted.current) { setRecording(false); setError(message) }
    try { await abandonedRecorder?.finish() } catch { /* interrupted recordings are never submitted */ }
    await saveChain.current.catch(() => undefined)
    const old = current.current
    if (old && !demo) {
      for (const segment of attempt.segments) await removeCountedFile(segment.path)
      try { if (isOwned()) publish(updateCountedSession(old.owner, old.id, s => {
        const found = s.attempts.find(a => a.id === attempt.id)
        if (found) { found.abandoned = true; found.segments = [] }
      })) } catch { if (mounted.current) setError('本地录像记录未能保存，请退出后重新进入检查。') }
    }
    if (demo && old) persist({ ...old, attempts: old.attempts.filter(a => a.id !== attempt.id) })
    try { if (!demo) await Taro.setKeepScreenOn({ keepScreenOn: false }) } catch { /* optional device feature */ }
    interrupting.current = false
  }

  async function start() {
    if (busy.current || interrupting.current || !ready || !cameraReady || !visible.current || !isOwned()) return
    const latest = current.current
    const done = latest ? completedAttempts(latest) : []
    if (done.length >= total || (done.length && Date.now() < Date.parse(done[done.length - 1].endedAt!) + 180000)) return
    busy.current = true; setProcessing(true); setError(''); audio.current?.stop()
    try {
      if (!demo) {
        await checkCountedStorage()
        // A successful refresh must still contain this immutable action snapshot.
        // A temporary network failure does not erase safely stored completed sets.
        const fresh = await fetchCurrentPrescriptionData().catch(error => {
          if (!latest || !done.length) throw error
          return undefined
        })
        if (fresh !== undefined && !fresh?.actions.some(a => a.id === action.id && a.dose_mode === 'sets')) {
          throw new Error('运动计划已更新，请返回运动计划开始新一次运动。已完成组会继续补传。')
        }
      }
      if (!visible.current || !isOwned()) return
      let next = (!demo && latest ? countedSessions(owner.current).find(s => s.id === latest.id) : latest) ?? newCountedSession(owner.current, { ...action, sets: total, repetitions: action.repetitions || 10 }, new Date().toISOString())
      const attempt: CountedAttempt = { id: createClientSessionId(), index: done.length + 1, startedAt: new Date().toISOString(),
        completed: false, segments: [], uploadId: createClientSessionId() }
      next = { ...next, exited: false, attempts: [...next.attempts, attempt] }
      persist(next); active.current = attempt; pendingEnd.current = null
      if (!demo) {
        const savedPaths = new Map<string, string>()
        const saveSegment = (path: string, durationMs: number) => {
          const delivery = saveChain.current.then(async () => {
            if (active.current?.id !== attempt.id) { await removeCountedFile(path); return }
            const saved = savedPaths.has(path) ? { savedFilePath: savedPaths.get(path)! } : await Taro.saveFile({ tempFilePath: path })
            if (!('savedFilePath' in saved) || !saved.savedFilePath) throw new Error('录像未能安全保存，请重试保存或重做本组')
            savedPaths.set(path, saved.savedFilePath)
            if (active.current?.id !== attempt.id) { await removeCountedFile(saved.savedFilePath); return }
            const info = await Taro.getFileInfo({ filePath: saved.savedFilePath })
            if (!('size' in info) || info.size <= 0) throw new Error('录像文件大小读取失败，请重试保存')
            const segment = { path: saved.savedFilePath, durationMs: Math.max(1, durationMs), sizeBytes: info.size }
            if (!attempt.segments.some(item => item.path === segment.path)) attempt.segments.push(segment)
            const changed = updateCountedSession(next.owner, next.id, s => {
              s.attempts.find(a => a.id === attempt.id)!.segments = [...attempt.segments]
            })
            publish(changed)
          })
          saveChain.current = delivery.catch(() => undefined)
          return delivery.catch(err => {
            if (!pendingEnd.current && active.current?.id === attempt.id) {
              // A save may have succeeded before metadata failed; include that file in abandonment cleanup.
              for (const savedPath of savedPaths.values()) {
                if (!attempt.segments.some(segment => segment.path === savedPath)) attempt.segments.push({ path: savedPath, durationMs: 0, sizeBytes: 0 })
              }
              void abandon('录像保存失败，本组未完成，请检查空间后重做。')
            }
            throw err
          })
        }
        recorder.current = new MotionTrainingRecorder({ camera: Taro.createCameraContext(), now: Date.now, onSegment: saveSegment,
          onStopped: endedAt => { if (pendingEnd.current && active.current?.id === attempt.id) pendingEnd.current = new Date(endedAt).toISOString() },
          maxDurationMs: 1800000, onMaxDuration: () => { void abandon('已达到单组录像时限，本组未完成，请休息后重做。') },
          onNativeError: () => { setTimeout(() => { void abandon('录像已中断，请重做本组。') }, 0) } })
        await recorder.current.start()
      }
      if (!visible.current || active.current?.id !== attempt.id) { await abandon('录像已中断，请重做本组'); return }
      attempt.startedAt = new Date().toISOString()
      if (demo) {
        if (!done.length) { next.startedAt = attempt.startedAt; next.trainingDate = shanghaiDate(Date.parse(attempt.startedAt)) }
        persist({ ...next, attempts: next.attempts.map(a => a.id === attempt.id ? attempt : a) })
      } else publish(updateCountedSession(next.owner, next.id, saved => {
        saved.attempts.find(a => a.id === attempt.id)!.startedAt = attempt.startedAt
        if (!done.length) { saved.startedAt = attempt.startedAt; saved.trainingDate = shanghaiDate(Date.parse(attempt.startedAt)) }
      }))
      setRecording(true)
      if (!demo) void Taro.setKeepScreenOn({ keepScreenOn: true }).catch(() => undefined)
    } catch (err) {
      if (active.current) await abandon('本组未开始，请重试')
      setError(err instanceof Error ? err.message : '无法开始本组，请重试')
    } finally { busy.current = false; if (mounted.current) setProcessing(false) }
  }

  async function finish() {
    if (busy.current || !active.current || !isOwned()) return
    busy.current = true; setProcessing(true); setError('')
    pendingEnd.current ??= new Date().toISOString()
    try {
      if (!demo) {
        if (recorder.current?.hasFailedSegment()) await recorder.current.retryFailedSegment()
        await recorder.current?.finish(); await saveChain.current
      }
      const attempt = active.current
      if (!attempt) return
      if (!demo && !attempt.segments.length) throw new Error('录像未能安全保存，请重试保存或重做本组')
      const complete = (s: CountedSession) => {
        const a = s.attempts.find(item => item.id === attempt.id)!
        a.completed = true; a.endedAt = pendingEnd.current!; a.segments = [...attempt.segments]
      }
      if (demo) { const copy = { ...current.current!, attempts: [...current.current!.attempts] }; complete(copy); persist(copy) }
      else publish(updateCountedSession(owner.current, current.current!.id, complete))
      const completed = completedAttempts(current.current!).length
      if (completed < total) audio.current?.begin(Date.parse(pendingEnd.current!) + 180000, total - completed)
      else audio.current?.stop()
      active.current = null; pendingEnd.current = null; recorder.current = null
      setRecording(false); setNow(Date.now()); void retry()
      if (!demo) void Taro.setKeepScreenOn({ keepScreenOn: false }).catch(() => undefined)
    } catch (err) { setError(err instanceof Error ? err.message : '保存失败，请重试保存或重做本组') }
    finally { busy.current = false; setProcessing(false) }
  }

  useDidHide(() => {
    visible.current = false; audio.current?.hide()
    if (active.current && !pendingEnd.current) void abandon('录像已中断，请重做本组。')
    const s = current.current
    if (s && !demo && isOwned()) publish(updateCountedSession(s.owner, s.id, item => { item.exited = true }))
  })
  useDidShow(() => {
    visible.current = true; setNow(Date.now()); audio.current?.show()
    const s = current.current
    if (s && s.exited && s.trainingDate !== shanghaiDate() && completedAttempts(s).length < s.plannedSets) {
      current.current = null; setSession(null); setError('已进入新的一天，将从第一组开始。此前已完成组会继续补传。')
    }
    void retry()
  })
  useEffect(() => {
    if (!recording) return
    const timer = setInterval(() => {
      if (active.current && Date.now() - Date.parse(active.current.startedAt) >= 1800000) void abandon('已达到单组录像时限，本组未完成，请休息后重做。')
    }, 1000)
    return () => clearInterval(timer)
  }, [recording])

  const done = session ? completedAttempts(session) : []
  const finished = done.length === total
  const restUntil = done.length && !finished ? Date.parse(done[done.length - 1].endedAt!) + 180000 : 0
  const left = Math.max(0, Math.ceil((restUntil - now) / 1000))
  const uploadErrors = done.filter(a => a.error).map(a => `第 ${a.index} 组：${a.error}`)
  return <View className='page counted-training-page'>
    <Text className='title'>{action.action_name}</Text>
    <Text className='counted-dose'>{action.count_unit === 'per_side' ? '每侧' : '每组'} {action.repetitions || 10} 个 · 共 {total} 组</Text>
    {action.count_unit === 'per_side' ? <Text className='muted'>左右各做 {action.repetitions || 10} 个，两侧做完后一起确认本组。</Text> : null}
    <Text className='section-title'>第 {Math.min(done.length + 1, total)}/{total} 组</Text>
    {!demo && !finished ? <Camera className='counted-camera' devicePosition='front' resolution='low' onInitDone={() => setCameraReady(true)} onError={() => { setCameraReady(false); void abandon('摄像头已中断，请检查权限后重做本组') }} onStop={() => { if (!pendingEnd.current) void abandon('录像已中断，请重做本组') }} /> : null}
    {demo ? <Text className='muted'>演示模式 · 不录制、不上传</Text> : null}
    {action.video_url && !action.video_unavailable && !finished ? <Video className='counted-preview' src={action.video_url} autoplay loop muted controls={false} /> : null}
    {finished ? <Text className='title'>{demo ? '演示运动已做完' : done.every(a => a.uploaded) ? '本次运动已完成' : '运动已做完，视频待上传'}</Text> : <>
      {restUntil > 0 && !recording ? <View className='counted-rest'>
        <Text>{left ? '组间休息' : '休息结束，请点击开始下一组'}</Text>
        <Text className='counted-timer'>{String(Math.floor(left / 60)).padStart(2, '0')}:{String(left % 60).padStart(2, '0')}</Text>
        <Text>还剩 {total - done.length} 组{left ? ' · 请充分休息' : ''}</Text>
      </View> : null}
      {recording ? <>
        <Text>请自行计数，做完后点击完成本组。</Text>
        {active.current && now - Date.parse(active.current.startedAt) > 1740000 ? <Text className='error'>即将达到单组录像时限，请及时完成或结束本组。</Text> : null}
        <Button className='primary-button full-button' disabled={processing} onClick={() => void finish()}>{pendingEnd.current ? '重试保存本组' : '完成本组'}</Button>
        {pendingEnd.current ? <Button onClick={() => void abandon('请重做本组')}>重做本组</Button> : null}
      </> : <Button className='primary-button full-button' disabled={left > 0 || processing || !ready || !cameraReady} onClick={() => void start()}>{done.length ? '开始下一组' : '开始本组'}</Button>}
    </>}
    {!demo && done.length ? <Text className='muted'>已做完 {done.length}/{total} 组 · 视频已上传 {done.filter(a => a.uploaded).length}/{done.length} 组</Text> : null}
    {audioError ? <Text className='muted'>语音暂不可用，请按屏幕倒计时休息。</Text> : null}
    {error ? <Text className='error'>{error}</Text> : null}
    {uploadErrors.map(message => <Text key={message} className='error'>{message}</Text>)}
    {finished ? <Button className='secondary-button' onClick={() => { current.current = null; setSession(null); setError(''); audio.current?.stop() }}>开始新一次运动</Button> : null}
    {!demo && done.some(a => !a.uploaded) ? <Button className='secondary-button' onClick={() => void retry()}>重试上传</Button> : null}
    <Button className='secondary-button' disabled={processing} onClick={async () => {
      if (active.current) { const result = await Taro.showModal({ title: '退出本组？', content: '本组尚未完成，退出后需要重做本组。已完成组会保留。', confirmText: '退出本组' }); if (!result.confirm) return; await abandon('') }
      void Taro.reLaunch({ url: '/pages/prescription/index' })
    }}>返回运动计划</Button>
  </View>
}
