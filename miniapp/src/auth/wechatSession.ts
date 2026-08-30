import Taro from '@tarojs/taro'

import { request } from '../api/client'
import type { BoundIdentity } from '../types/patientApp'

export type WechatSessionResponse =
  | { status: 'unbound' }
  | ({ status: 'authenticated'; token: string | null } & BoundIdentity)

export type BindResponse = BoundIdentity & { token: string }

async function freshWxCode(): Promise<string> {
  const result = await Taro.login()
  if (!result.code) throw new Error('微信登录失败，请重试')
  return result.code
}

export async function recoverWechatSession(): Promise<WechatSessionResponse> {
  const wxCode = await freshWxCode()
  return request<WechatSessionResponse>('/patient-app/wechat-session/', {
    method: 'POST',
    data: { wx_code: wxCode }
  })
}

export async function bindWechatAccount(code: string): Promise<BindResponse> {
  const wxCode = await freshWxCode()
  return request<BindResponse>('/patient-app/bind/', {
    method: 'POST',
    data: { code, wx_code: wxCode }
  })
}
