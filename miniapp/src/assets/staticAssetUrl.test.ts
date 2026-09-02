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
  ])('拒绝%s', (relativePath) => {
    expect(() => staticAssetUrl(relativePath, 'https://cdn.example.com/assets')).toThrow('固定素材路径无效')
  })
})
