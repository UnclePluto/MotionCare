import { Button, Input, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useCallback, useEffect, useRef, useState } from 'react'

import { bindWechatAccount, recoverWechatSession } from '../../auth/wechatSession'
import { clearPatientAppToken, setPatientAppToken } from '../../auth/token'
import { DEMO_BINDING_CODE, isDemoSession, startDemoSession } from '../../demo/session'
import { stopPendingGameUploadRetryLoop } from '../game-session/retryUpload'

type LoginCheckState = 'checking' | 'unbound' | 'error'
const HOME_NAVIGATION_ERROR = '进入首页失败，请重新检查登录'

function normalizeBindingCode(value: string) {
  return value.replace(/\D/g, '').slice(0, 4)
}

async function redirectToHome(): Promise<void> {
  try {
    await Taro.redirectTo({ url: '/pages/home/index' })
  } catch {
    throw new Error(HOME_NAVIGATION_ERROR)
  }
}

export default function BindPage() {
  const [loginCheckState, setLoginCheckState] = useState<LoginCheckState>('checking')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [inputFocused, setInputFocused] = useState(true)
  const mountedRef = useRef(true)
  const activeRequestRef = useRef<'check' | 'bind' | null>(null)
  const requestVersionRef = useRef(0)
  const codeDigits = Array.from({ length: 4 }, (_, index) => code[index] ?? '')
  const canSubmit = loginCheckState === 'unbound' && code.length === 4 && !loading

  useEffect(() => () => {
    mountedRef.current = false
    requestVersionRef.current += 1
  }, [])

  const checkExistingBinding = useCallback(async () => {
    if (activeRequestRef.current) return

    const requestVersion = requestVersionRef.current + 1
    requestVersionRef.current = requestVersion
    activeRequestRef.current = 'check'
    setLoginCheckState('checking')
    setError('')

    try {
      if (isDemoSession()) {
        await redirectToHome()
        return
      }

      const body = await recoverWechatSession()
      if (!mountedRef.current || requestVersionRef.current !== requestVersion) return

      if (body.status === 'unbound') {
        clearPatientAppToken()
        setLoginCheckState('unbound')
        return
      }

      if (body.token) setPatientAppToken(body.token)
      await redirectToHome()
    } catch (err) {
      if (!mountedRef.current || requestVersionRef.current !== requestVersion) return
      setError(err instanceof Error ? err.message : '登录检查失败，请重试')
      setLoginCheckState('error')
    } finally {
      if (requestVersionRef.current === requestVersion) {
        activeRequestRef.current = null
      }
    }
  }, [])

  useDidShow(checkExistingBinding)

  async function submit() {
    if (loginCheckState !== 'unbound' || loading || activeRequestRef.current) return

    const normalizedCode = normalizeBindingCode(code)
    if (normalizedCode.length !== 4) return

    if (normalizedCode === DEMO_BINDING_CODE) {
      startDemoSession()
      stopPendingGameUploadRetryLoop()
      Taro.redirectTo({ url: '/pages/home/index' })
      return
    }

    setLoading(true)
    setError('')
    const requestVersion = requestVersionRef.current + 1
    requestVersionRef.current = requestVersion
    activeRequestRef.current = 'bind'
    let bindingSucceeded = false
    try {
      const body = await bindWechatAccount(normalizedCode)
      if (!mountedRef.current || requestVersionRef.current !== requestVersion) return
      setPatientAppToken(body.token)
      bindingSucceeded = true
      await redirectToHome()
    } catch (err) {
      if (!mountedRef.current || requestVersionRef.current !== requestVersion) return
      setError(err instanceof Error ? err.message : '绑定失败')
      if (bindingSucceeded) setLoginCheckState('error')
    } finally {
      if (mountedRef.current && requestVersionRef.current === requestVersion) {
        setLoading(false)
        activeRequestRef.current = null
      }
    }
  }

  const heroDescription = loginCheckState === 'unbound'
    ? '输入指导老师提供的绑定码，开始你的运动训练。'
    : loginCheckState === 'error'
      ? '暂时无法确认登录状态，请重新检查。'
      : '正在恢复登录，请稍候。'

  return (
    <View className='page bind-page'>
      <View className='page-hero bind-hero'>
        <Text className='eyebrow'>欢迎使用</Text>
        <Text className='title'>绑定 MotionCare</Text>
        <Text className='muted'>{heroDescription}</Text>
      </View>
      {loginCheckState === 'checking' ? (
        <View className='panel bind-card'>
          <Text className='label'>正在恢复登录</Text>
          <Text className='muted'>正在检查登录状态，请稍候。</Text>
        </View>
      ) : loginCheckState === 'error' ? (
        <View className='panel bind-card'>
          <Text className='error'>{error}</Text>
          <Button className='primary-button' onClick={checkExistingBinding}>
            重新检查登录
          </Button>
        </View>
      ) : (
        <View className='panel bind-card'>
          <Text className='label'>绑定码</Text>
          <Text className='muted'>请输入指导老师提供的 4 位数字绑定码</Text>
          <View className='code-input-wrap' onClick={() => setInputFocused(true)}>
            <Input
              className='code-input'
              value={code}
              type='number'
              maxlength={4}
              focus={inputFocused}
              placeholder=''
              confirmType='done'
              onFocus={() => setInputFocused(true)}
              onBlur={() => setInputFocused(false)}
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
            绑定账号
          </Button>
        </View>
      )}
    </View>
  )
}
