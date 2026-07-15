export function resolveApiBaseUrl(configuredUrl: string, platform: string): string {
  if (platform === 'devtools') {
    return configuredUrl.replace(/^http:\/\/[^/:]+(?=:8000(?:\/|$))/, 'http://127.0.0.1')
  }
  return configuredUrl
}
