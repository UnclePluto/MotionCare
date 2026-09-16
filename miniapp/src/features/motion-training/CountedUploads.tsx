import { Button, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'
import { getPatientAppToken } from '../../auth/token'
import { fetchPatientHomeData } from '../../demo/patientAppData'
import { isDemoSession } from '../../demo/session'
import { COUNTED_QUEUE_KEY, completedAttempts, countedSessions, syncCountedQueue, type CountedSession } from './countedSession'

/** Keeps old-plan completed videos reachable after the current action has changed. */
export default function CountedUploads() {
  const [items, setItems] = useState<CountedSession[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const mounted = useRef(true)
  const loading = useRef(false)
  async function load(retry = false) {
    if (loading.current || isDemoSession() || !getPatientAppToken() || !Taro.getStorageSync(COUNTED_QUEUE_KEY)) return
    loading.current = true
    const token = getPatientAppToken()
    const owned = () => mounted.current && token === getPatientAppToken() && !isDemoSession()
    setBusy(retry)
    try {
      const home = await fetchPatientHomeData()
      if (!owned()) return
      if (retry) await syncCountedQueue(home.project_patient_id)
      if (!owned()) return
      setItems(countedSessions(home.project_patient_id).filter(s => completedAttempts(s).some(a => !a.uploaded)))
      setError('')
    } catch (err) { if (owned()) setError(err instanceof Error ? err.message : '待上传录像读取失败') }
    finally { loading.current = false; if (owned()) setBusy(false) }
  }
  useDidShow(() => { void load() })
  useEffect(() => {
    void load()
    const timer = setInterval(() => { void load() }, 15000)
    return () => { mounted.current = false; clearInterval(timer) }
  }, [])
  if (!items.length && !error) return null
  return <View className='panel counted-pending'>
    <Text className='section-title'>运动视频待上传</Text>
    {items.map(item => <View key={item.id} className='history-row'>
      <Text className='value'>{item.actionName} · {item.trainingDate}</Text>
      <Text className='muted'>已做完 {completedAttempts(item).length}/{item.plannedSets} 组 · 视频已上传 {completedAttempts(item).filter(a => a.uploaded).length}/{item.plannedSets} 组</Text>
      {completedAttempts(item).filter(a => a.error).map(a => <Text key={a.id} className='error'>第 {a.index} 组：{a.error}</Text>)}
    </View>)}
    {error ? <Text className='error'>{error}</Text> : null}
    <Text className='muted'>已完成组无需重做。补传成功后计入原运动日期。</Text>
    <Button className='secondary-button' loading={busy} disabled={busy} onClick={() => void load(true)}>重试上传运动视频</Button>
  </View>
}
