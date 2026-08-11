import { neutralizeMiniappMessage } from '../copy/neutralTerminology'

export function containsSensitiveCredentialText(message: string): boolean {
  return /authorization|bearer|token|secret|access[_-]?key|credential[_-]?id/i.test(message) ||
    /\b(?:AK|SK)\b\s*[:=]/.test(message)
}

export function networkRequestErrorMessage(error: unknown): string {
  const fallback = '请求失败，请检查网络后重试'
  let detail = ''

  if (error && typeof error === 'object') {
    const errMsg = (error as { errMsg?: unknown }).errMsg
    if (typeof errMsg === 'string') detail = errMsg
  } else if (typeof error === 'string') {
    detail = error
  }

  detail = detail.replace(/\s+/g, ' ').trim()
  if (!detail || containsSensitiveCredentialText(detail)) return fallback
  return `网络请求失败：${neutralizeMiniappMessage(detail.slice(0, 180))}`
}
