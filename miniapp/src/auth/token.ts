import Taro from '@tarojs/taro'

const TOKEN_KEY = 'motioncare_patient_app_token'

export function getPatientAppToken(): string | undefined {
  return Taro.getStorageSync<string>(TOKEN_KEY) || undefined
}

export function setPatientAppToken(token: string) {
  Taro.setStorageSync(TOKEN_KEY, token)
}

export function clearPatientAppToken() {
  Taro.removeStorageSync(TOKEN_KEY)
}
