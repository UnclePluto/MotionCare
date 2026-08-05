import Taro from '@tarojs/taro'

import { clearCurrentPrescriptionCache } from '../pages/prescription/cache'

const TOKEN_KEY = 'motioncare_patient_app_token'

export function getPatientAppToken(): string | undefined {
  return Taro.getStorageSync<string>(TOKEN_KEY) || undefined
}

export function setPatientAppToken(token: string) {
  clearCurrentPrescriptionCache()
  Taro.setStorageSync(TOKEN_KEY, token)
}

export function clearPatientAppToken() {
  clearCurrentPrescriptionCache()
  Taro.removeStorageSync(TOKEN_KEY)
}
