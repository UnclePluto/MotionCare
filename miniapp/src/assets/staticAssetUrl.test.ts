import { describe, expect, it } from 'vitest'

import { staticAssetUrl } from './staticAssetUrl'

describe('staticAssetUrl', () => {
  it('规范化基础地址尾斜杠和素材路径首尾斜杠', () => {
    expect(staticAssetUrl(
      '/v-a1/file.webp/',
      'https://cdn.example.com/assets///',
    )).toBe('https://cdn.example.com/assets/v-a1/file.webp')
  })

  it.each([
    ['', '空路径'],
    ['/', '仅斜杠路径'],
    ['../file.webp', '上级路径'],
    ['v-a1/../file.webp', '嵌入上级路径'],
    ['https://cdn.example.com/file.webp', '绝对 URL'],
    ['//cdn.example.com/file.webp', '协议相对 URL'],
    ['?v=a1', '仅 query 路径'],
    ['#preview', '仅 fragment 路径'],
    ['%2e%2e/private.webp', '小写百分号编码的上级路径'],
    ['%2E%2E/private.webp', '大写百分号编码的上级路径'],
    ['v-a1/%252e%252e/private.webp', '双重编码的上级路径'],
    ['v-a1/%25252e%25252e/private.webp', '嵌套编码的上级路径'],
    ['v-a1/file%2.webp', '非法百分号转义'],
  ])('拒绝%s', (relativePath) => {
    expect(() => staticAssetUrl(relativePath, 'https://cdn.example.com/assets')).toThrow('固定素材路径无效')
  })

  it('保留合法文件名中的百分号编码', () => {
    expect(staticAssetUrl(
      'v-a1/file%20name.webp',
      'https://cdn.example.com/assets',
    )).toBe('https://cdn.example.com/assets/v-a1/file%20name.webp')
  })
})
