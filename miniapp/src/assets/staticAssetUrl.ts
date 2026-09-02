export function staticAssetUrl(
  relativePath: string,
  baseUrl = process.env.TARO_APP_ASSET_BASE_URL,
): string {
  const isInvalid = typeof relativePath !== 'string'
    || !relativePath.trim()
    || relativePath.startsWith('//')
    || /^[a-z][a-z0-9+.-]*:/i.test(relativePath)
    || relativePath.startsWith('?')
    || relativePath.startsWith('#')
    || relativePath.split('/').includes('..')

  if (isInvalid || !baseUrl) {
    throw new Error('固定素材路径无效')
  }

  const normalizedPath = relativePath.replace(/^\/+|\/+$/g, '')
  if (!normalizedPath) {
    throw new Error('固定素材路径无效')
  }
  return `${baseUrl.replace(/\/+$/, '')}/${normalizedPath}`
}
