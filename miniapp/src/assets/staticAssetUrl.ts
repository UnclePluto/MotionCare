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

export function normalizeStaticAssetBaseUrl(baseUrl: string): string {
  const value = typeof baseUrl === 'string' ? baseUrl.trim() : ''
  if (!value || value.includes('\\')) {
    throw new Error('固定素材基础地址无效')
  }

  let parsed: URL
  try {
    parsed = new URL(value)
  } catch {
    throw new Error('固定素材基础地址无效')
  }
  if (
    (parsed.protocol !== 'http:' && parsed.protocol !== 'https:')
    || parsed.username
    || parsed.password
    || value.includes('?')
    || value.includes('#')
  ) {
    throw new Error('固定素材基础地址无效')
  }

  const pathname = parsed.pathname.replace(/\/+$/, '')
  parsed.pathname = pathname || '/'
  return pathname ? parsed.href : parsed.origin
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
  const resolved = new URL(normalizedPath, base)
  if (
    resolved.origin !== base.origin
    || !resolved.pathname.startsWith(base.pathname)
  ) {
    throw new Error('固定素材路径无效')
  }
  return resolved.href
}
