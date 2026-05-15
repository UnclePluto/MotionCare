import Taro from '@tarojs/taro'

import { clearPatientAppToken, getPatientAppToken } from '../auth/token'

const API_BASE_URL = process.env.TARO_APP_API_BASE_URL || 'http://127.0.0.1:8000/api'

type Method = 'GET' | 'POST' | 'PUT'

type RequestOptions = {
  method?: Method
  data?: unknown
}

function resolveErrorMessage(data: unknown): string {
  if (data && typeof data === 'object') {
    const detail = (data as { detail?: unknown }).detail
    const message = (data as { message?: unknown }).message
    if (typeof detail === 'string') return detail
    if (typeof message === 'string') return message
  }
  return '请求失败'
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const token = getPatientAppToken()
  const response = await Taro.request<T>({
    url: `${API_BASE_URL}${path}`,
    method: options.method ?? 'GET',
    data: options.data,
    header: {
      'content-type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    }
  })

  if (response.statusCode === 401 || response.statusCode === 403) {
    clearPatientAppToken()
    Taro.redirectTo({ url: '/pages/bind/index' })
    throw new Error('登录已失效')
  }
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw new Error(resolveErrorMessage(response.data))
  }
  return response.data
}
