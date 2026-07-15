import { describe, expect, it } from 'vitest'

import { resolveApiBaseUrl } from './baseUrl'

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
