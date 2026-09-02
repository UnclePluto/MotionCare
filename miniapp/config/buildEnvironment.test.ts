import { describe, expect, it } from 'vitest'

import {
  resolveApiBaseUrl,
  resolveAssetBaseUrl,
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

  it('正式微信构建要求绝对 HTTPS 素材地址', () => {
    expect(() => resolveAssetBaseUrl({
      configuredUrl: '',
      target: 'weapp',
      environment: 'production',
    })).toThrow('素材地址')
    expect(() => resolveAssetBaseUrl({
      configuredUrl: 'http://cdn.example.com/assets',
      target: 'weapp',
      environment: 'production',
    })).toThrow('HTTPS')
    expect(resolveAssetBaseUrl({
      configuredUrl: 'https://cdn.example.com/assets/',
      target: 'weapp',
      environment: 'production',
    })).toBe('https://cdn.example.com/assets')
  })

  it('开发微信构建接受绝对 HTTP 或 HTTPS 素材地址', () => {
    expect(resolveAssetBaseUrl({
      configuredUrl: 'http://localhost:9000/assets/',
      target: 'weapp',
      environment: 'development',
    })).toBe('http://localhost:9000/assets')
  })

  it('非微信构建未配置素材地址时返回空字符串', () => {
    expect(resolveAssetBaseUrl({
      configuredUrl: '',
      target: 'h5',
      environment: 'production',
    })).toBe('')
  })
})
