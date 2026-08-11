import { beforeEach, describe, expect, it, vi } from 'vitest'

const taroMocks = vi.hoisted(() => ({
  request: vi.fn(),
  getDeviceInfo: vi.fn(() => ({ platform: 'ios' })),
  getStorageSync: vi.fn(),
  setStorageSync: vi.fn(),
  removeStorageSync: vi.fn(),
  redirectTo: vi.fn()
}))
const prescriptionCacheMocks = vi.hoisted(() => ({
  clearCurrentPrescriptionCache: vi.fn()
}))

vi.mock('@tarojs/taro', () => ({ default: taroMocks }))
vi.mock('../pages/prescription/cache', () => prescriptionCacheMocks)

import { request, safeApiErrorMessage } from './client'
import { resolveApiBaseUrl } from './baseUrl'
import * as safeError from './safeError'
import { clearPatientAppToken, setPatientAppToken } from '../auth/token'

beforeEach(() => {
  vi.clearAllMocks()
  taroMocks.getDeviceInfo.mockReturnValue({ platform: 'ios' })
})

describe('小程序 API 地址', () => {
  it('开发者工具使用本机回环地址', () => {
    expect(resolveApiBaseUrl('http://10.21.53.102:8000/api', 'devtools')).toBe(
      'http://127.0.0.1:8000/api',
    )
  })

  it('真机保留局域网地址', () => {
    expect(resolveApiBaseUrl('http://10.21.53.102:8000/api', 'ios')).toBe(
      'http://10.21.53.102:8000/api',
    )
  })
})

describe('小程序网络错误', () => {
  it('保留微信请求失败原因用于真机诊断', () => {
    expect(safeError.networkRequestErrorMessage({
      errMsg: 'request:fail url not in domain list',
    })).toBe('网络请求失败：request:fail url not in domain list')
  })

  it('转换网络错误中的医疗相关提示词', () => {
    expect(safeError.networkRequestErrorMessage({
      errMsg: 'request:fail 医疗诊疗医嘱治疗医院疾病病人康复',
    })).toBe('网络请求失败：request:fail 运动服务运动指导运动说明训练服务机构身体情况用户运动')
  })
})

describe('小程序 API 错误', () => {
  it('转换安全 API 错误中的医疗相关提示词', () => {
    expect(safeApiErrorMessage({
      detail: '患者处方已更新，请联系医生或医护',
    })).toBe('用户运动计划已更新，请联系指导老师或指导老师')
  })
})

describe('患者凭据与处方缓存生命周期', () => {
  it('设置和清除 token 时都清空当前处方缓存', () => {
    setPatientAppToken('new-token')
    clearPatientAppToken()

    expect(prescriptionCacheMocks.clearCurrentPrescriptionCache).toHaveBeenCalledTimes(2)
    expect(taroMocks.setStorageSync).toHaveBeenCalledWith(
      'motioncare_patient_app_token',
      'new-token'
    )
    expect(taroMocks.removeStorageSync).toHaveBeenCalledWith('motioncare_patient_app_token')
  })

  it.each([401, 403])('收到 %s 时清空 token 与处方缓存并返回绑定页', async (statusCode) => {
    taroMocks.request.mockResolvedValueOnce({ statusCode, data: {} })

    await expect(request('/patient-app/home/')).rejects.toThrow('登录已失效')

    expect(prescriptionCacheMocks.clearCurrentPrescriptionCache).toHaveBeenCalledTimes(1)
    expect(taroMocks.removeStorageSync).toHaveBeenCalledWith('motioncare_patient_app_token')
    expect(taroMocks.redirectTo).toHaveBeenCalledWith({ url: '/pages/bind/index' })
  })
})
