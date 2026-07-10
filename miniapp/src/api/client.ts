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

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`
}

export function patientAuthorizationHeader(): Record<string, string> {
  const token = getPatientAppToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function handlePatientUnauthorized(): never {
  clearPatientAppToken()
  Taro.redirectTo({ url: '/pages/bind/index' })
  throw new Error('登录已失效')
}

export function safeApiErrorMessage(data: unknown): string {
  const message = resolveErrorMessage(data)
  if (/authorization|bearer|token|secret/i.test(message)) return '请求失败'
  return message
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await Taro.request<T>({
    url: apiUrl(path),
    method: options.method ?? 'GET',
    data: options.data,
    header: {
      'content-type': 'application/json',
      ...patientAuthorizationHeader()
    }
  })

  if (response.statusCode === 401 || response.statusCode === 403) {
    handlePatientUnauthorized()
  }
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw new Error(safeApiErrorMessage(response.data))
  }
  return response.data
}
