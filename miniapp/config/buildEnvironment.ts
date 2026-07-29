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
