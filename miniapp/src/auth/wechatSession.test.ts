import { beforeEach, describe, expect, it, vi } from 'vitest'

import { bindWechatAccount, recoverWechatSession } from './wechatSession'

const taroMock = vi.hoisted(() => ({
  login: vi.fn()
}))
const requestMock = vi.hoisted(() => vi.fn())

vi.mock('@tarojs/taro', () => ({
  default: taroMock
}))

vi.mock('../api/client', () => ({
  request: requestMock
}))

describe('微信会话 API', () => {
  beforeEach(() => {
    taroMock.login.mockReset()
    requestMock.mockReset()
  })

  it('恢复与真实绑定每次都获取新的微信 code', async () => {
    taroMock.login
      .mockResolvedValueOnce({ code: 'startup-code' })
      .mockResolvedValueOnce({ code: 'binding-code-login' })
    requestMock
      .mockResolvedValueOnce({ status: 'unbound' })
      .mockResolvedValueOnce({
        token: 'token',
        project_patient_id: 1,
        patient: { id: 1, name: '王阿姨' },
        project: { id: 1, name: '居家运动项目' }
      })

    await recoverWechatSession()
    await bindWechatAccount('1234')

    expect(requestMock).toHaveBeenNthCalledWith(1, '/patient-app/wechat-session/', {
      method: 'POST',
      data: { wx_code: 'startup-code' }
    })
    expect(requestMock).toHaveBeenNthCalledWith(2, '/patient-app/bind/', {
      method: 'POST',
      data: { code: '1234', wx_code: 'binding-code-login' }
    })
  })

  it('微信登录没有返回 code 时提示重试且不发送请求', async () => {
    taroMock.login.mockResolvedValueOnce({ code: '' })

    await expect(recoverWechatSession()).rejects.toThrow('微信登录失败，请重试')

    expect(requestMock).not.toHaveBeenCalled()
  })
})
