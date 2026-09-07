import { normalizeStaticAssetBaseUrl } from '../../shared/staticAssetBaseUrl.js'

function hasForbiddenPathSyntax(path: string): boolean {
  return /[\\?#]/.test(path)
    || path.split('/').some((segment) => segment === '.' || segment === '..')
}

function hasUnsafeRelativePath(relativePath: string): boolean {
  let decoded = relativePath
  for (let round = 0; round <= relativePath.length; round += 1) {
    if (hasForbiddenPathSyntax(decoded) || /%(?:2f|5c)/i.test(decoded)) {
      return true
    }

    let next: string
    try {
      next = decodeURIComponent(decoded)
    } catch {
      return true
    }
    if (next === decoded) return false
    decoded = next
  }
  return true
}

export function staticAssetUrl(
  relativePath: string,
  baseUrl = process.env.TARO_APP_ASSET_BASE_URL,
): string {
  const isInvalid = typeof relativePath !== 'string'
    || !relativePath.trim()
    || relativePath.startsWith('//')
    || /^[a-z][a-z0-9+.-]*:/i.test(relativePath)
    || hasUnsafeRelativePath(relativePath)

  if (isInvalid || !baseUrl) {
    throw new Error('固定素材路径无效')
  }

  const normalizedPath = relativePath.replace(/^\/+|\/+$/g, '')
  if (!normalizedPath) {
    throw new Error('固定素材路径无效')
  }

  let normalizedBaseUrl: string
  try {
    normalizedBaseUrl = normalizeStaticAssetBaseUrl(baseUrl)
  } catch {
    throw new Error('固定素材路径无效')
  }
  const base = new URL(`${normalizedBaseUrl}/`)
  // Taro 4.2 的 URL polyfill 会忽略第二个参数中的 pathname，因此先拼成绝对地址。
  const resolved = new URL(`${normalizedBaseUrl}/${normalizedPath}`)
  if (
    resolved.origin !== base.origin
    || !resolved.pathname.startsWith(base.pathname)
  ) {
    throw new Error('固定素材路径无效')
  }
  return resolved.href
}

export { normalizeStaticAssetBaseUrl } from '../../shared/staticAssetBaseUrl.js'
