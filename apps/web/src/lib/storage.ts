const PREFIX = 'hermes.companion.'

export const storage = {
  get(key: string): string {
    return localStorage.getItem(PREFIX + key) || ''
  },
  set(key: string, value: string): void {
    if (value) localStorage.setItem(PREFIX + key, value)
    else localStorage.removeItem(PREFIX + key)
  },
  remove(key: string): void {
    localStorage.removeItem(PREFIX + key)
  },
  clearAuth(): void {
    for (const key of ['access', 'refresh', 'accessExpires', 'refreshExpires', 'user']) {
      localStorage.removeItem(PREFIX + key)
    }
  }
}

export function normalizedBridgeUrl(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, '')
  if (!trimmed) return ''
  const parsed = new URL(trimmed)
  if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error('Bridge URL must use HTTP or HTTPS')
  return parsed.toString().replace(/\/$/, '')
}

export function apiBase(): string {
  return storage.get('bridgeUrl')
}
