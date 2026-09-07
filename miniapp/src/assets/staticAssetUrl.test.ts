import { afterEach, describe, expect, it, vi } from 'vitest'
import { TaroURLProvider } from '../../node_modules/@tarojs/runtime/dist/bom/URL.js'

vi.hoisted(() => Object.assign(globalThis, {
  ENABLE_INNER_HTML: false,
  ENABLE_ADJACENT_HTML: false,
  ENABLE_CLONE_NODE: false,
  ENABLE_CONTAINS: false,
  ENABLE_SIZE_APIS: false,
  ENABLE_TEMPLATE_CONTENT: false,
}))

import { parseSignedAssetManifest } from './signedAssetManifest'
import { signedAssetFixture } from './signedAssetFixtures.test-helper'
import { staticAssetUrl } from './staticAssetUrl'

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs() })

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
    ['./file.webp', '当前目录路径'],
    ['../file.webp', '上级路径'],
    ['v-a1/../file.webp', '嵌入上级路径'],
    ['v-a1\\file.webp', '反斜杠分隔符'],
    ['v-a1\\..\\secret.webp', '反斜杠上级路径'],
    ['v-a1/file.webp?download=1', '路径内 query'],
    ['v-a1/file.webp#preview', '路径内 fragment'],
    ['https://cdn.example.com/file.webp', '绝对 URL'],
    ['//cdn.example.com/file.webp', '协议相对 URL'],
    ['?v=a1', '仅 query 路径'],
    ['#preview', '仅 fragment 路径'],
    ['%2e/file.webp', '小写百分号编码的当前目录'],
    ['%2E/file.webp', '大写百分号编码的当前目录'],
    ['%2e%2e/private.webp', '小写百分号编码的上级路径'],
    ['%2E%2E/private.webp', '大写百分号编码的上级路径'],
    ['v-a1/%252e%252e/private.webp', '双重编码的上级路径'],
    ['v-a1/%25252e%25252e/private.webp', '嵌套编码的上级路径'],
    ['v-a1/file%2fsecret.webp', '小写百分号编码的斜杠'],
    ['v-a1/file%2Fsecret.webp', '大写百分号编码的斜杠'],
    ['v-a1/file%5csecret.webp', '小写百分号编码的反斜杠'],
    ['v-a1/file%5Csecret.webp', '大写百分号编码的反斜杠'],
    ['v-a1/file%252Fsecret.webp', '双重编码的斜杠'],
    ['v-a1/file%255csecret.webp', '双重编码的反斜杠'],
    ['v-a1/file%25252fsecret.webp', '三重编码的斜杠'],
    ['v-a1/file%3Fdownload.webp', '百分号编码的 query 分隔符'],
    ['v-a1/file%23preview.webp', '百分号编码的 fragment 分隔符'],
    ['v-a1/file%2.webp', '非法百分号转义'],
    ['v-a1/file%25ZZ.webp', '递归解码后的非法百分号转义'],
  ])('拒绝%s', (relativePath) => {
    expect(() => staticAssetUrl(relativePath, 'https://cdn.example.com/assets')).toThrow('固定素材路径无效')
  })

  it.each([
    'https://user@cdn.example.com/assets',
    'https://user:secret@cdn.example.com/assets',
    'https://cdn.example.com/assets?token=public',
    'https://cdn.example.com/assets#preview',
  ])('拒绝含凭据、query 或 fragment 的基础地址：%s', (baseUrl) => {
    expect(() => staticAssetUrl('v-a1/file.webp', baseUrl)).toThrow('固定素材路径无效')
  })

  it('使用安全 URL 构造且保持结果在基础路径子树内', () => {
    const result = staticAssetUrl(
      '/v-a1/nested/file.webp/',
      'https://cdn.example.com/motioncare/static-assets///',
    )

    expect(result).toBe(
      'https://cdn.example.com/motioncare/static-assets/v-a1/nested/file.webp',
    )
    const parsed = new URL(result)
    expect(parsed.origin).toBe('https://cdn.example.com')
    expect(parsed.pathname.startsWith('/motioncare/static-assets/')).toBe(true)
  })

  it('保留合法文件名中的百分号编码', () => {
    expect(staticAssetUrl(
      'v-a1/file%20name.webp',
      'https://cdn.example.com/assets',
    )).toBe('https://cdn.example.com/assets/v-a1/file%20name.webp')
  })

  it('使用 Taro URL 实现时仍保留基础地址目录并解析完整签名清单', () => {
    vi.stubGlobal('URL', TaroURLProvider)
    vi.stubEnv('TARO_APP_ASSET_BASE_URL', 'https://cdn.example.com/motioncare/static-assets')

    expect(staticAssetUrl(
      'v-a1/file.webp',
      'https://cdn.example.com/motioncare/static-assets',
    )).toBe('https://cdn.example.com/motioncare/static-assets/v-a1/file.webp')
    expect(Object.keys(parseSignedAssetManifest(signedAssetFixture())).length).toBeGreaterThan(0)
    expect(Object.keys(parseSignedAssetManifest(signedAssetFixture()).urls)).toHaveLength(23)
  })
})
