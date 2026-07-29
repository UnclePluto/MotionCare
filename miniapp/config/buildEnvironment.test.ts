import { describe, expect, it } from 'vitest'

import {
  resolveApiBaseUrl,
  resolveConfigEnvironment,
} from './buildEnvironment'

describe('小程序构建环境', () => {
  it('开发构建只读取 development 配置', () => {
    expect(resolveConfigEnvironment({
      NODE_ENV: 'production',
      TARO_APP_CONFIG_ENV: 'development',
    })).toBe('development')
  })

  it('正式微信小程序构建拒绝非 HTTPS 地址', () => {
    expect(() => resolveApiBaseUrl({
      configuredUrl: 'http://10.0.0.2:8000/api',
      target: 'weapp',
      environment: 'production',
    })).toThrow('HTTPS')
  })

  it('正式 H5 构建允许同源相对 API 地址', () => {
    expect(resolveApiBaseUrl({
      configuredUrl: '/api',
      target: 'h5',
      environment: 'production',
    })).toBe('/api')
  })
})
