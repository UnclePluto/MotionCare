import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'


const ALLOWED_CONTENT_TYPES = new Set(['image/webp', 'audio/mp4'])

function sha256(body) {
  return createHash('sha256').update(body).digest('hex')
}

function publicBaseUrl(baseUrl) {
  let parsed
  try {
    parsed = new URL(baseUrl)
  } catch {
    throw new Error('固定素材公开 base URL 无效')
  }
  if (parsed.protocol !== 'https:') {
    throw new Error('固定素材公开 base URL 必须使用 HTTPS')
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error('固定素材公开 base URL 不得包含凭据、查询参数或片段')
  }
  return parsed.href.replace(/\/$/, '')
}

async function loadManifest(manifestPath) {
  let manifest
  try {
    manifest = JSON.parse(await readFile(manifestPath, 'utf8'))
  } catch {
    throw new Error('固定素材清单无法读取')
  }
  if (!manifest || typeof manifest !== 'object' || !Array.isArray(manifest.entries)) {
    throw new Error('固定素材清单格式无效')
  }
  if (manifest.entries.length !== 23) {
    throw new Error('固定素材清单必须包含 23 项')
  }
  if (typeof manifest.assetVersion !== 'string' || !manifest.assetVersion) {
    throw new Error('固定素材清单版本无效')
  }
  return manifest
}

function validateEntry(entry, assetVersion) {
  if (!entry || typeof entry !== 'object') {
    throw new Error('固定素材清单项格式无效')
  }
  const requiredFields = ['key', 'contentType', 'sizeBytes', 'sha256', 'relativePath']
  if (requiredFields.some((field) => !(field in entry))) {
    throw new Error('固定素材清单项缺少字段')
  }
  if (typeof entry.key !== 'string' || !entry.key) {
    throw new Error('固定素材清单 key 无效')
  }
  if (entry.kind !== 'game-image' && entry.kind !== 'motion-instruction-audio') {
    throw new Error(`固定素材 kind 无效：${entry.key}`)
  }
  const expectedContentType = entry.kind === 'game-image' ? 'image/webp' : 'audio/mp4'
  if (!ALLOWED_CONTENT_TYPES.has(entry.contentType) || entry.contentType !== expectedContentType) {
    throw new Error(`固定素材媒体类型不允许：${entry.key}`)
  }
  if (!Number.isSafeInteger(entry.sizeBytes) || entry.sizeBytes < 0) {
    throw new Error(`固定素材字节数无效：${entry.key}`)
  }
  if (typeof entry.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(entry.sha256)) {
    throw new Error(`固定素材 SHA-256 无效：${entry.key}`)
  }
  if (typeof entry.relativePath !== 'string' || !entry.relativePath) {
    throw new Error(`固定素材相对路径无效：${entry.key}`)
  }
  const parts = entry.relativePath.split('/')
  if (
    entry.relativePath.includes('\\')
    || parts.some((part) => !part || part === '.' || part === '..')
    || parts[0] !== assetVersion
  ) {
    throw new Error(`固定素材相对路径无效：${entry.key}`)
  }
}

function requireHeader(response, name, key) {
  const value = response.headers.get(name)
  if (!value) throw new Error(`固定素材缺少 ${name}：${key}`)
  return value
}

async function verifyEntry({ entry, assetVersion, baseUrl, fetchImpl }) {
  validateEntry(entry, assetVersion)
  const url = `${baseUrl}/${entry.relativePath}`
  let response
  try {
    response = await fetchImpl(url)
  } catch {
    throw new Error(`固定素材公开 URL 请求失败：${entry.key}`)
  }
  if (!response || response.status !== 200) {
    throw new Error(`固定素材公开 URL 必须返回 HTTP 200：${entry.key}`)
  }

  const body = Buffer.from(await response.arrayBuffer())
  if (body.byteLength !== entry.sizeBytes) {
    throw new Error(`固定素材公开正文的字节数不匹配：${entry.key}`)
  }
  const contentLength = requireHeader(response, 'Content-Length', entry.key)
  if (!/^\d+$/.test(contentLength) || Number(contentLength) !== entry.sizeBytes) {
    throw new Error(`固定素材公开响应 Content-Length 不匹配：${entry.key}`)
  }
  if (sha256(body) !== entry.sha256) {
    throw new Error(`固定素材公开正文 SHA-256 不匹配：${entry.key}`)
  }

  const contentType = requireHeader(response, 'Content-Type', entry.key)
    .split(';', 1)[0]
    .trim()
    .toLowerCase()
  if (contentType !== entry.contentType) {
    throw new Error(`固定素材公开响应媒体类型不匹配：${entry.key}`)
  }

  const cacheControl = requireHeader(response, 'Cache-Control', entry.key)
  const cacheDirectives = new Set(
    cacheControl.toLowerCase().split(',').map((directive) => directive.trim()),
  )
  if (!cacheDirectives.has('max-age=31536000')) {
    throw new Error(`固定素材公开响应缺少 max-age=31536000：${entry.key}`)
  }
  if (!cacheDirectives.has('immutable')) {
    throw new Error(`固定素材公开响应缺少 immutable：${entry.key}`)
  }

  return { key: entry.key, url, sizeBytes: entry.sizeBytes }
}

export async function verifyStaticAssets({ manifestPath, baseUrl, fetchImpl = fetch }) {
  const manifest = await loadManifest(manifestPath)
  const canonicalBaseUrl = publicBaseUrl(baseUrl)
  const verified = []
  for (const entry of manifest.entries) {
    verified.push(await verifyEntry({
      entry,
      assetVersion: manifest.assetVersion,
      baseUrl: canonicalBaseUrl,
      fetchImpl,
    }))
  }
  return verified
}

function parseArguments(argv) {
  const values = new Map()
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index]
    if (argument !== '--manifest' && argument !== '--base-url') {
      throw new Error(`未知参数：${argument}`)
    }
    const value = argv[index + 1]
    if (!value || value.startsWith('--')) {
      throw new Error(`参数 ${argument} 缺少值`)
    }
    values.set(argument, value)
    index += 1
  }
  if (!values.has('--manifest') || !values.has('--base-url')) {
    throw new Error('必须提供 --manifest 与 --base-url')
  }
  return {
    manifestPath: values.get('--manifest'),
    baseUrl: values.get('--base-url'),
  }
}

async function main() {
  const options = parseArguments(process.argv.slice(2))
  const verified = await verifyStaticAssets(options)
  for (const asset of verified) {
    console.log(`${asset.key} ${asset.url} ${asset.sizeBytes} 已验证`)
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    await main()
  } catch (error) {
    console.error(error instanceof Error ? error.message : '固定素材公开 URL 校验失败')
    process.exitCode = 1
  }
}
