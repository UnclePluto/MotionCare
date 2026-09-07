import { isRequestCanceled, PublicRequestError, publicRequest } from '../api/client'
import { STATIC_ASSET_MANIFEST } from './staticAssetManifest.generated'
import { staticAssetUrl } from './staticAssetUrl'

export type StaticAssetKey = typeof STATIC_ASSET_MANIFEST.entries[number]['key']
export type SignedAssetManifest = {
  assetVersion: string
  issuedAt: number
  expiresAt: number
  urls: Record<StaticAssetKey, string>
}

export class SignedAssetManifestError extends Error {
  constructor(public readonly retryable: boolean) {
    super('训练素材暂时不可用，请稍后重试')
    this.name = 'SignedAssetManifestError'
  }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (!value || typeof value !== 'object') return false
  const prototype = Object.getPrototypeOf(value)
  return prototype === Object.prototype || prototype === null
}

function signedUrl(value: unknown, relativePath: string, expiresAt: number): string {
  if (typeof value !== 'string' || /[\\#\s]/.test(value)) throw new SignedAssetManifestError(false)
  const expected = new URL(staticAssetUrl(relativePath))
  const url = new URL(value)
  // URL 会折叠点路径；先检查原始路径，不能让穿越路径通过归一化比较。
  const rawParts = value.match(/^https:\/\/([^/?#]+)([^?#]*)/)
  const rawPath = rawParts?.[2]
  if (!rawPath || rawParts?.[1].includes('@')
    || rawPath.split('/').some((part) => /^\.{1,2}$/.test(part.replace(/%2e/ig, '.')))
    || url.protocol !== 'https:' || url.origin !== expected.origin
    || url.pathname !== expected.pathname || url.username || url.password || url.hash) {
    throw new SignedAssetManifestError(false)
  }
  const query = url.searchParams
  const keys = Array.from(query.keys())
  const token = query.get('token')
  if (keys.length !== 2 || query.getAll('e').length !== 1 || query.getAll('token').length !== 1
    || query.get('e') !== String(expiresAt) || !token || !/^[A-Za-z0-9_-]+:[A-Za-z0-9_-]+=*$/.test(token)) {
    throw new SignedAssetManifestError(false)
  }
  return value
}

export function parseSignedAssetManifest(value: unknown): SignedAssetManifest {
  try {
    if (!isPlainObject(value) || !Number.isSafeInteger(value.issued_at) || !Number.isSafeInteger(value.expires_at)) {
      throw new SignedAssetManifestError(false)
    }
    const issuedAt = value.issued_at as number
    const expiresAt = value.expires_at as number
    const ttl = expiresAt - issuedAt
    if (ttl < 120 || ttl > 3600 || value.asset_version !== STATIC_ASSET_MANIFEST.assetVersion
      || !Array.isArray(value.assets) || value.assets.length !== STATIC_ASSET_MANIFEST.entries.length) {
      throw new SignedAssetManifestError(false)
    }
    const urls = {} as Record<StaticAssetKey, string>
    const seen = new Set<string>()
    for (const asset of value.assets) {
      if (!isPlainObject(asset)) throw new SignedAssetManifestError(false)
      const expected = STATIC_ASSET_MANIFEST.entries.find((entry) => entry.key === asset.key)
      if (!expected || seen.has(expected.key) || asset.relative_path !== expected.relativePath
        || asset.content_type !== expected.contentType || asset.size_bytes !== expected.sizeBytes
        || asset.sha256 !== expected.sha256) {
        throw new SignedAssetManifestError(false)
      }
      seen.add(expected.key)
      urls[expected.key] = signedUrl(asset.url, expected.relativePath, expiresAt)
    }
    return { assetVersion: STATIC_ASSET_MANIFEST.assetVersion, issuedAt, expiresAt, urls }
  } catch {
    throw new SignedAssetManifestError(false)
  }
}

export function mayRefreshSignedAssets(error: unknown): boolean {
  if (error instanceof SignedAssetManifestError) return error.retryable
  if (error instanceof PublicRequestError) return error.statusCode >= 500 && error.statusCode < 600
  return !isRequestCanceled(error)
}

type CachedManifest = { manifest: SignedAssetManifest; startedAt: number; usableUntil: number }
type InflightManifest = {
  generation: number
  startedAt: number
  force: boolean
  promise: Promise<SignedAssetManifest>
}
let cached: CachedManifest | undefined
let inflight: InflightManifest | undefined
let generation = 0
let clockEpoch = 0
let lastObservedAt: number | undefined

function observeTime(): number {
  const now = Date.now()
  if (lastObservedAt !== undefined && now < lastObservedAt) {
    cached = undefined
    inflight = undefined
    generation += 1
    clockEpoch += 1
  }
  lastObservedAt = now
  return now
}

export function fetchSignedAssetManifest(options: { forceRefresh?: boolean } = {}): Promise<SignedAssetManifest> {
  const startedAt = observeTime()
  const force = options.forceRefresh === true
  if (inflight && (!force || inflight.force)) return inflight.promise
  if (!force && cached && startedAt >= cached.startedAt && startedAt < cached.usableUntil) {
    return Promise.resolve(cached.manifest)
  }
  cached = undefined
  const requestGeneration = ++generation
  const requestClockEpoch = clockEpoch
  // executor 同步发起请求；then/catch 在 inflight 登记后执行，连同步抛错也不会留下拒绝缓存。
  const response = new Promise<unknown>((resolve) => {
    resolve(publicRequest<unknown>('/patient-app/static-assets/?version=' + encodeURIComponent(STATIC_ASSET_MANIFEST.assetVersion)))
  })
  const promise = response.then((value) => {
    const manifest = parseSignedAssetManifest(value)
    const now = observeTime()
    const usableUntil = startedAt + (manifest.expiresAt - manifest.issuedAt) * 1000 - 60_000
    if (requestClockEpoch !== clockEpoch || now < startedAt || now >= usableUntil) {
      throw new SignedAssetManifestError(true)
    }
    // 已换代的成功结果仅返回原调用者，不能覆盖强制刷新的结果。
    if (requestGeneration === generation) {
      cached = { manifest, startedAt, usableUntil }
      inflight = undefined
    }
    return manifest
  }).catch((error: unknown) => {
    if (requestGeneration === generation) inflight = undefined
    throw new SignedAssetManifestError(mayRefreshSignedAssets(error))
  })
  inflight = { generation: requestGeneration, startedAt, force, promise }
  return promise
}
