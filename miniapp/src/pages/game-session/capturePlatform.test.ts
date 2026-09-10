import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@tarojs/taro', () => ({
  default: {
    getPerformance: vi.fn(),
  },
}))

import Taro from '@tarojs/taro'

import { createCaptureNow, createGameClientSessionId } from './capturePlatform'

afterEach(() => {
  vi.mocked(Taro.getPerformance).mockReset()
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('capture platform', () => {
  it('H5使用绑定到原对象的全局性能时钟', () => {
    vi.stubEnv('TARO_ENV', 'h5')
    const performanceClock = {
      value: 123,
      now() {
        return this.value
      },
    }
    vi.stubGlobal('performance', performanceClock)

    expect(createCaptureNow()()).toBe(123)
    expect(Taro.getPerformance).not.toHaveBeenCalled()
  })

  it('微信优先使用绑定到平台性能对象的时钟', () => {
    vi.stubEnv('TARO_ENV', 'weapp')
    const platformClock = {
      value: 456,
      now() {
        return this.value
      },
    }
    vi.mocked(Taro.getPerformance).mockReturnValue(platformClock as never)
    vi.stubGlobal('performance', { now: () => 999 })

    expect(createCaptureNow()()).toBe(456)
  })

  it('性能接口缺失时明确失败', () => {
    vi.stubEnv('TARO_ENV', 'weapp')
    vi.mocked(Taro.getPerformance).mockReturnValue({} as never)
    vi.stubGlobal('performance', undefined)

    expect(() => createCaptureNow()).toThrow('当前环境不支持单调性能时钟')
  })

  it('微信getPerformance方法缺失时使用全局时钟，无全局时钟则明确失败', () => {
    vi.stubEnv('TARO_ENV', 'weapp')
    const original = Taro.getPerformance
    Object.defineProperty(Taro, 'getPerformance', {value: undefined, configurable: true, writable: true})
    try {
      vi.stubGlobal('performance', {now: () => 321})
      expect(createCaptureNow()()).toBe(321)
      vi.stubGlobal('performance', undefined)
      expect(() => createCaptureNow()).toThrow('当前环境不支持单调性能时钟')
    } finally {
      Object.defineProperty(Taro, 'getPerformance', {value: original, configurable: true, writable: true})
    }
  })

  it('生成UUID v4格式且1000次无重复', () => {
    const ids = Array.from({ length: 1000 }, () => createGameClientSessionId())

    expect(ids.every(id => /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id))).toBe(true)
    expect(new Set(ids)).toHaveLength(1000)
  })
})
