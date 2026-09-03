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

  it.each([
    ['', '空地址'],
    ['/motioncare/static-assets', '相对地址'],
    ['http://cdn.example.com/assets', 'HTTP 地址'],
    ['ftp://cdn.example.com/assets', '非 HTTP 协议'],
  ])('正式 H5 构建在构建环境解析期拒绝%s', (configuredUrl) => {
    expect(() => resolveAssetBaseUrl({
      configuredUrl,
      target: 'h5',
      environment: 'production',
    })).toThrow('素材地址')
  })

  it('正式 H5 构建接受显式 HTTPS CDN 地址', () => {
    expect(resolveAssetBaseUrl({
      configuredUrl: 'https://cdn.example.com/motioncare/static-assets/',
      target: 'h5',
      environment: 'production',
    })).toBe('https://cdn.example.com/motioncare/static-assets')
  })

  it.each([
    'https://user@cdn.example.com/assets',
    'https://user:secret@cdn.example.com/assets',
    'https://cdn.example.com/assets?token=public',
    'https://cdn.example.com/assets#preview',
  ])('构建期拒绝含凭据、query 或 fragment 的素材基础地址：%s', (configuredUrl) => {
    expect(() => resolveAssetBaseUrl({
      configuredUrl,
      target: 'h5',
      environment: 'development',
    })).toThrow('素材地址')
  })

  it('开发微信构建接受绝对 HTTP 或 HTTPS 素材地址', () => {
    expect(resolveAssetBaseUrl({
      configuredUrl: 'http://localhost:9000/assets/',
      target: 'weapp',
      environment: 'development',
    })).toBe('http://localhost:9000/assets')
  })

  it('非正式 H5 构建未配置素材地址时返回空字符串', () => {
    expect(resolveAssetBaseUrl({
      configuredUrl: '',
      target: 'h5',
      environment: 'development',
    })).toBe('')
  })
})
