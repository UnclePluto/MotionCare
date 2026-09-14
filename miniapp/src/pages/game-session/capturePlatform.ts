import Taro from '@tarojs/taro'

type Clock = {
  now: () => number
}

type PerformanceProvider = {
  getPerformance?: () => unknown
}

function isClock(value: unknown): value is Clock {
  return typeof value === 'object'
    && value !== null
    && 'now' in value
    && typeof value.now === 'function'
}

export function createCaptureNow(): () => number {
  if (process.env.TARO_ENV === 'weapp') {
    const platform = Taro as unknown as PerformanceProvider
    if (typeof platform.getPerformance === 'function') {
      const platformPerformance = platform.getPerformance()
      if (isClock(platformPerformance)) return platformPerformance.now.bind(platformPerformance)
    }
  }

  const globalPerformance: unknown = globalThis.performance
  if (isClock(globalPerformance)) return globalPerformance.now.bind(globalPerformance)

  throw new Error('当前环境不支持单调性能时钟')
}

export function createGameClientSessionId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, marker => {
    const value = marker === 'x'
      ? Math.floor(Math.random() * 16)
      : Math.floor(Math.random() * 4) + 8
    return value.toString(16)
  })
}
