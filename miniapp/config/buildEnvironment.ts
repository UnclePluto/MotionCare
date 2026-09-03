import { normalizeStaticAssetBaseUrl } from '../src/assets/staticAssetUrl'

type EnvironmentSource = {
  NODE_ENV?: string
  TARO_APP_CONFIG_ENV?: string
}

export type ConfigEnvironment = 'development' | 'test' | 'production'

export function resolveConfigEnvironment(
  source: EnvironmentSource,
): ConfigEnvironment {
  const explicit = source.TARO_APP_CONFIG_ENV
  if (explicit === 'development' || explicit === 'test' || explicit === 'production') {
    return explicit
  }
  if (source.NODE_ENV === 'test') return 'test'
  if (source.NODE_ENV === 'production') return 'production'
  return 'development'
}

export function resolveApiBaseUrl(input: {
  configuredUrl?: string
  target?: string
  environment: ConfigEnvironment
}): string {
  const value = input.configuredUrl?.trim() || 'http://127.0.0.1:8000/api'
  if (input.target === 'weapp' && input.environment === 'production') {
    let parsed: URL
    try {
      parsed = new URL(value)
    } catch {
      throw new Error('正式微信小程序必须配置绝对 HTTPS API 地址')
    }
    if (parsed.protocol !== 'https:') {
      throw new Error('正式微信小程序 API 地址必须使用 HTTPS')
    }
  }
  return value
}

export function resolveAssetBaseUrl(input: {
  configuredUrl?: string
  target?: string
  environment: ConfigEnvironment
}): string {
  const value = input.configuredUrl?.trim() || ''
  const requiresAssetBaseUrl = input.target === 'weapp'
    || (input.target === 'h5' && input.environment === 'production')

  if (!value) {
    if (requiresAssetBaseUrl) {
      throw new Error('当前构建目标必须配置绝对素材地址')
    }
    return ''
  }

  let normalized: string
  try {
    normalized = normalizeStaticAssetBaseUrl(value)
  } catch {
    throw new Error('素材地址必须是不含凭据、查询参数或片段的绝对 HTTP 或 HTTPS 地址')
  }
  const parsed = new URL(normalized)
  if (requiresAssetBaseUrl && input.environment === 'production' && parsed.protocol !== 'https:') {
    throw new Error('正式构建素材地址必须使用 HTTPS')
  }
  return normalized
}
