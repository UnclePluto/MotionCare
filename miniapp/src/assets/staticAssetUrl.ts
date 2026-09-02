const MAX_PATH_DECODE_ROUNDS = 4

function hasEncodedPathTraversal(relativePath: string): boolean {
  return relativePath.split('/').some((segment) => {
    let decoded = segment
    for (let round = 0; round < MAX_PATH_DECODE_ROUNDS; round += 1) {
      let next: string
      try {
        next = decodeURIComponent(decoded)
      } catch {
        return true
      }
      if (next.split('/').includes('..')) return true
      if (next === decoded) return false
      decoded = next
    }
    return true
  })
}

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
    || hasEncodedPathTraversal(relativePath)

  if (isInvalid || !baseUrl) {
    throw new Error('固定素材路径无效')
  }

  const normalizedPath = relativePath.replace(/^\/+|\/+$/g, '')
  if (!normalizedPath) {
    throw new Error('固定素材路径无效')
  }
  return `${baseUrl.replace(/\/+$/, '')}/${normalizedPath}`
}
