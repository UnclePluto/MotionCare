import { Button, Input, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'

import { request } from '../../api/client'
import { getPatientAppToken, setPatientAppToken } from '../../auth/token'
import type { BoundIdentity } from '../../types/patientApp'

type BindResponse = BoundIdentity & {
  token: string
}

function normalizeBindingCode(value: string) {
  return value.replace(/\D/g, '').slice(0, 4)
}

export default function BindPage() {
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const codeDigits = Array.from({ length: 4 }, (_, index) => code[index] ?? '')
  const canSubmit = code.length === 4 && !loading

  useDidShow(() => {
    if (getPatientAppToken()) {
      Taro.redirectTo({ url: '/pages/home/index' })
    }
  })

  async function submit() {
    if (loading) return

    const normalizedCode = normalizeBindingCode(code)
    if (normalizedCode.length !== 4) return

    setLoading(true)
    setError('')
    try {
      const login = await Taro.login()
      const wxOpenid = login.code || 'dev-openid'
      const body = await request<BindResponse>('/patient-app/bind/', {
        method: 'POST',
        data: { code: normalizedCode, wx_openid: wxOpenid }
      })
      setPatientAppToken(body.token)
      Taro.redirectTo({ url: '/pages/home/index' })
    } catch (err) {
      setError(err instanceof Error ? err.message : '绑定失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <View className='page bind-page'>
      <Text className='title'>绑定 MotionCare</Text>
      <View className='panel'>
        <Text className='label'>绑定码</Text>
        <Text className='muted'>请输入医生提供的 4 位数字绑定码</Text>
        <View className='code-input-wrap'>
          <Input
            className='code-input'
            value={code}
            type='number'
            placeholder='请输入4位绑定码'
            focus
            onInput={(event) => setCode(normalizeBindingCode(event.detail.value))}
          />
          <View className='code-slots'>
            {codeDigits.map((digit, index) => (
              <View className={`code-slot${digit ? ' filled' : ''}`} key={index}>
                <Text className='code-slot-text'>{digit}</Text>
              </View>
            ))}
          </View>
        </View>
        {error ? <Text className='error'>{error}</Text> : null}
        <Button
          className='primary-button'
          loading={loading}
          disabled={!canSubmit}
          onClick={submit}
        >
          绑定
        </Button>
      </View>
    </View>
  )
}
