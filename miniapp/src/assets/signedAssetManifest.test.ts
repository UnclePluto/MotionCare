import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { signedAssetFixture } from './signedAssetFixtures.test-helper'

const api = vi.hoisted(() => ({ publicRequest: vi.fn() }))
vi.mock('@tarojs/taro', () => ({ default: {} }))
vi.mock('../api/client', async (importOriginal) => ({
  ...await importOriginal<typeof import('../api/client')>(),
  publicRequest: api.publicRequest,
}))
beforeEach(() => {
  vi.resetModules()
  api.publicRequest.mockReset()
  vi.useFakeTimers()
  vi.setSystemTime(0)
  vi.stubEnv('TARO_APP_ASSET_BASE_URL', 'https://cdn.example.com/motioncare/static-assets')
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllEnvs() })
function deferred() {
  let resolve!: (value: ReturnType<typeof signedAssetFixture>) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<ReturnType<typeof signedAssetFixture>>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
type Fixture = ReturnType<typeof signedAssetFixture>
const mutations: [string, (fixture: Fixture) => unknown][] = [
  ['null', () => null], ['数组', () => []], ['非普通对象', () => new Date()],
  ['缺项', (f) => { f.assets.pop() }],
  ['重复 key', (f) => { f.assets[1] = { ...f.assets[0] } }],
  ['未知 key', (f) => { Object.assign(f.assets[0], { key: 'unexpected' }) }],
  ['错误版本', (f) => { Object.assign(f, { asset_version: 'other-version' }) }],
  ['错误 sha', (f) => { Object.assign(f.assets[0], { sha256: '0'.repeat(64) }) }],
  ['错误大小', (f) => { Object.assign(f.assets[0], { size_bytes: 1 }) }],
  ['错误类型', (f) => { Object.assign(f.assets[0], { content_type: 'image/png' }) }],
  ['错误路径', (f) => { Object.assign(f.assets[0], { relative_path: 'other.webp' }) }],
  ['HTTP', (f) => { f.assets[0].url = f.assets[0].url.replace('https:', 'http:') }],
  ['跨域', (f) => { f.assets[0].url = f.assets[0].url.replace('cdn.example.com', 'evil.example.com') }],
  ['路径穿越', (f) => { f.assets[0].url = f.assets[0].url.replace('/static-assets/', '/static-assets/extra/../') }],
  ['编码路径穿越', (f) => { f.assets[0].url = f.assets[0].url.replace('/static-assets/', '/static-assets/extra/%2e%2e/') }],
  ['反斜杠', (f) => { f.assets[0].url = f.assets[0].url.replace('/static-assets/', '/static-assets/\\') }],
  ['userinfo', (f) => { f.assets[0].url = f.assets[0].url.replace('https://', 'https://user:password@') }],
  ['空 userinfo', (f) => { f.assets[0].url = f.assets[0].url.replace('https://', 'https://@') }],
  ['空用户名密码', (f) => { f.assets[0].url = f.assets[0].url.replace('https://', 'https://:@') }],
  ['fragment', (f) => { f.assets[0].url += '#fragment' }],
  ['空 fragment', (f) => { f.assets[0].url += '#' }],
  ['缺 token', (f) => { f.assets[0].url = f.assets[0].url.split('&token=')[0] }],
  ['空 token', (f) => { f.assets[0].url = f.assets[0].url.split('&token=')[0] + '&token=' }],
  ['无签名冒号', (f) => { f.assets[0].url = f.assets[0].url.replace('fixture%3Asignature', 'invalid') }],
  ['重复 e', (f) => { f.assets[0].url += '&e=' + f.expires_at }],
  ['重复 token', (f) => { f.assets[0].url += '&token=fixture%3Asignature' }],
  ['未知 query', (f) => { f.assets[0].url += '&other=1' }],
  ['非法 query 编码', (f) => { f.assets[0].url += '&x=%' }],
  ['e 不匹配', (f) => { f.assets[0].url = f.assets[0].url.replace('e=1800000600', 'e=1800000601') }],
  ['非整数 issued_at', (f) => { f.issued_at += 0.5 }],
  ['非整数 expires_at', (f) => { f.expires_at += 0.5 }],
  ['字符串时戳', (f) => { Object.assign(f, { issued_at: '1800000000' }) }],
  ['TTL 小于 120', (f) => { f.expires_at = f.issued_at + 119 }],
  ['TTL 大于 3600', (f) => { f.expires_at = f.issued_at + 3601 }],
]
describe('签名清单校验', () => {
  it('提取完整 23 项地址，不透传原始字段', async () => {
    const { parseSignedAssetManifest } = await import('./signedAssetManifest')
    const fixture = signedAssetFixture()
    const manifest = parseSignedAssetManifest(fixture)
    expect(Object.keys(manifest.urls)).toHaveLength(23)
    expect(manifest).toEqual({ assetVersion: 'v-3aafe09211fd', issuedAt: 1_800_000_000,
      expiresAt: 1_800_000_600, urls: Object.fromEntries(fixture.assets.map((asset) => [asset.key, asset.url])) })
  })
  it.each(mutations)('拒绝%s，错误不含签名 URL', async (_, mutate) => {
    const { parseSignedAssetManifest, SignedAssetManifestError } = await import('./signedAssetManifest')
    const fixture = signedAssetFixture()
    const result = mutate(fixture)
    let error: unknown
    try { parseSignedAssetManifest(result === undefined ? fixture : result) } catch (caught) { error = caught }
    expect(error).toBeInstanceOf(SignedAssetManifestError)
    expect(error).toMatchObject({ retryable: false, message: '训练素材暂时不可用，请稍后重试' })
  })
  it.each([120, 3600])('接受 TTL 边界 %s 秒', async (ttl) => {
    const { parseSignedAssetManifest } = await import('./signedAssetManifest')
    const fixture = signedAssetFixture()
    fixture.expires_at = fixture.issued_at + ttl
    fixture.assets.forEach((asset) => { asset.url = asset.url.replace('e=1800000600', 'e=' + fixture.expires_at) })
    expect(parseSignedAssetManifest(fixture).expiresAt).toBe(fixture.expires_at)
  })
})
describe('内存签名缓存', () => {
  it('同版本请求合并，540 秒后更新签名', async () => {
    api.publicRequest.mockResolvedValue(signedAssetFixture())
    const { fetchSignedAssetManifest } = await import('./signedAssetManifest')
    await Promise.all([fetchSignedAssetManifest(), fetchSignedAssetManifest()])
    expect(api.publicRequest).toHaveBeenCalledTimes(1)
    expect(api.publicRequest).toHaveBeenCalledWith('/patient-app/static-assets/?version=v-3aafe09211fd')
    vi.setSystemTime(539_000)
    await fetchSignedAssetManifest()
    expect(api.publicRequest).toHaveBeenCalledTimes(1)
    vi.setSystemTime(540_000)
    await fetchSignedAssetManifest()
    expect(api.publicRequest).toHaveBeenCalledTimes(2)
  })
  it('从请求开始扣除 30 秒网络耗时', async () => {
    const pending = deferred()
    api.publicRequest.mockReturnValueOnce(pending.promise).mockResolvedValue(signedAssetFixture())
    const { fetchSignedAssetManifest } = await import('./signedAssetManifest')
    const request = fetchSignedAssetManifest()
    vi.setSystemTime(30_000)
    pending.resolve(signedAssetFixture())
    await request
    vi.setSystemTime(539_999)
    await fetchSignedAssetManifest()
    expect(api.publicRequest).toHaveBeenCalledTimes(1)
    vi.setSystemTime(540_000)
    await fetchSignedAssetManifest()
    expect(api.publicRequest).toHaveBeenCalledTimes(2)
  })
  it('响应已无安全窗口则拒绝，后续请求可重试', async () => {
    const pending = deferred()
    api.publicRequest.mockReturnValueOnce(pending.promise).mockResolvedValue(signedAssetFixture())
    const { fetchSignedAssetManifest } = await import('./signedAssetManifest')
    const request = fetchSignedAssetManifest()
    vi.setSystemTime(540_000)
    pending.resolve(signedAssetFixture())
    await expect(request).rejects.toMatchObject({ retryable: true })
    await fetchSignedAssetManifest()
    expect(api.publicRequest).toHaveBeenCalledTimes(2)
  })
  it('命中后时钟回拨，即使晚于 startedAt 也刷新', async () => {
    api.publicRequest.mockResolvedValue(signedAssetFixture())
    const { fetchSignedAssetManifest } = await import('./signedAssetManifest')
    await fetchSignedAssetManifest()
    vi.setSystemTime(100_000)
    await fetchSignedAssetManifest()
    vi.setSystemTime(90_000)
    await fetchSignedAssetManifest()
    expect(api.publicRequest).toHaveBeenCalledTimes(2)
  })
  it('第一次拒绝不会永久缓存 rejected Promise', async () => {
    api.publicRequest.mockRejectedValueOnce(new Error('network https://private?token=secret')).mockResolvedValueOnce(signedAssetFixture())
    const { fetchSignedAssetManifest } = await import('./signedAssetManifest')
    await expect(fetchSignedAssetManifest()).rejects.toMatchObject({ retryable: true, message: '训练素材暂时不可用，请稍后重试' })
    await expect(fetchSignedAssetManifest()).resolves.toHaveProperty('urls.pattern_sun')
    expect(api.publicRequest).toHaveBeenCalledTimes(2)
  })
  it('同步抛错也不会遗留被拒绝的在途请求', async () => {
    api.publicRequest.mockImplementationOnce(() => { throw new Error('network') }).mockResolvedValueOnce(signedAssetFixture())
    const { fetchSignedAssetManifest } = await import('./signedAssetManifest')
    await expect(fetchSignedAssetManifest()).rejects.toMatchObject({ retryable: true })
    await expect(fetchSignedAssetManifest()).resolves.toHaveProperty('urls.pattern_sun')
    expect(api.publicRequest).toHaveBeenCalledTimes(2)
  })
  it('响应返回时观察到回拨，拒绝当前清单并允许重试', async () => {
    vi.setSystemTime(100_000)
    const pending = deferred()
    api.publicRequest.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(signedAssetFixture())
    const { fetchSignedAssetManifest } = await import('./signedAssetManifest')
    const result = fetchSignedAssetManifest()
    vi.setSystemTime(90_000)
    pending.resolve(signedAssetFixture())
    await expect(result).rejects.toMatchObject({ retryable: true })
    await expect(fetchSignedAssetManifest()).resolves.toHaveProperty('urls.pattern_sun')
    expect(api.publicRequest).toHaveBeenCalledTimes(2)
  })
  it('并发强制刷新合并且普通请求等待新结果', async () => {
    const pending = deferred()
    api.publicRequest.mockResolvedValueOnce(signedAssetFixture()).mockReturnValueOnce(pending.promise)
    const { fetchSignedAssetManifest } = await import('./signedAssetManifest')
    await fetchSignedAssetManifest()
    const first = fetchSignedAssetManifest({ forceRefresh: true })
    const second = fetchSignedAssetManifest({ forceRefresh: true })
    const normal = fetchSignedAssetManifest()
    pending.resolve(signedAssetFixture(1_800_000_001, 'new:signature'))
    const results = await Promise.all([first, second, normal])
    expect(api.publicRequest).toHaveBeenCalledTimes(2)
    results.forEach((manifest) => expect(manifest.issuedAt).toBe(1_800_000_001))
  })
  it.each(['成功', '失败'])('旧请求迟到%s不能清掉新请求', async (outcome) => {
    const old = deferred(); const fresh = deferred()
    api.publicRequest.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise)
    const { fetchSignedAssetManifest } = await import('./signedAssetManifest')
    const oldResult = fetchSignedAssetManifest().catch((error) => error)
    const refreshing = fetchSignedAssetManifest({ forceRefresh: true })
    if (outcome === '成功') old.resolve(signedAssetFixture())
    else old.reject(new Error('network'))
    await expect(oldResult).resolves.toMatchObject(outcome === '成功' ? { issuedAt: 1_800_000_000 } : { retryable: true })
    const concurrent = fetchSignedAssetManifest()
    expect(api.publicRequest).toHaveBeenCalledTimes(2)
    fresh.resolve(signedAssetFixture(1_800_000_100))
    await Promise.all([refreshing, concurrent])
    expect((await fetchSignedAssetManifest()).issuedAt).toBe(1_800_000_100)
  })
  it('旧普通请求晚于强制刷新返回，只返回原调用者而不覆盖新缓存', async () => {
    const old = deferred()
    api.publicRequest.mockReturnValueOnce(old.promise).mockResolvedValueOnce(signedAssetFixture(1_800_000_100))
    const { fetchSignedAssetManifest } = await import('./signedAssetManifest')
    const oldResult = fetchSignedAssetManifest()
    await fetchSignedAssetManifest({ forceRefresh: true })
    old.resolve(signedAssetFixture())
    expect((await oldResult).issuedAt).toBe(1_800_000_000)
    expect((await fetchSignedAssetManifest()).issuedAt).toBe(1_800_000_100)
  })
  it('时钟回拨使在途旧请求失效，新请求可完成', async () => {
    vi.setSystemTime(100_000)
    const old = deferred()
    api.publicRequest.mockReturnValueOnce(old.promise).mockResolvedValueOnce(signedAssetFixture(1_800_000_100))
    const { fetchSignedAssetManifest } = await import('./signedAssetManifest')
    const oldResult = fetchSignedAssetManifest().catch((error) => error)
    vi.setSystemTime(90_000)
    await fetchSignedAssetManifest()
    old.resolve(signedAssetFixture())
    await expect(oldResult).resolves.toMatchObject({ retryable: true })
    expect((await fetchSignedAssetManifest()).issuedAt).toBe(1_800_000_100)
  })
})
describe('签名错误重试分型', () => {
  it.each([400, 401, 403, 404, 405, 429, 500, 503])('HTTP %s 仅服务端错误允许自动刷新', async (status) => {
    const { PublicRequestError } = await import('../api/client')
    const { fetchSignedAssetManifest, mayRefreshSignedAssets } = await import('./signedAssetManifest')
    const error = new PublicRequestError('https://private?token=secret', status)
    expect(mayRefreshSignedAssets(error)).toBe(status >= 500)
    api.publicRequest.mockRejectedValueOnce(error)
    const result = await fetchSignedAssetManifest().catch((caught) => caught)
    expect(result).toMatchObject({ message: '训练素材暂时不可用，请稍后重试', retryable: status >= 500 })
  })
  it('parser 错误不刷新，网络错误允许刷新', async () => {
    const { fetchSignedAssetManifest, mayRefreshSignedAssets, SignedAssetManifestError } = await import('./signedAssetManifest')
    api.publicRequest.mockResolvedValueOnce({ assets: [] })
    expect(mayRefreshSignedAssets(await fetchSignedAssetManifest().catch((caught) => caught))).toBe(false)
    expect(mayRefreshSignedAssets(new SignedAssetManifestError(true))).toBe(true)
    expect(mayRefreshSignedAssets(new Error('network'))).toBe(true)
  })
  it.each([{ name: 'AbortError' }, { code: 'ERR_CANCELED' }, { errMsg: 'request:fail abort' }, { errMsg: 'request:fail cancel' }])('取消不可重试 %j', async (error) => {
    const { fetchSignedAssetManifest, mayRefreshSignedAssets } = await import('./signedAssetManifest')
    expect(mayRefreshSignedAssets(error)).toBe(false)
    api.publicRequest.mockRejectedValueOnce(error)
    await expect(fetchSignedAssetManifest()).rejects.toMatchObject({ retryable: false })
  })
})
