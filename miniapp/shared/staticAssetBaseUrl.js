function normalizeStaticAssetBaseUrl(baseUrl) {
  const value = typeof baseUrl === 'string' ? baseUrl.trim() : ''
  if (!value || value.includes('\\')) {
    throw new Error('固定素材基础地址无效')
  }

  let parsed
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

module.exports = { normalizeStaticAssetBaseUrl }
