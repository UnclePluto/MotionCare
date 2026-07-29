export function containsSensitiveCredentialText(message: string): boolean {
  return /authorization|bearer|token|secret|access[_-]?key|credential[_-]?id/i.test(message) ||
    /\b(?:AK|SK)\b\s*[:=]/.test(message)
}
