import { apiBase, storage } from './storage'
import type { Tokens } from '../types'

let refreshPromise: Promise<boolean> | null = null

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `Request failed (${status})`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

function endpoint(path: string): string {
  return `${apiBase()}${path.startsWith('/') ? path : `/${path}`}`
}

function saveTokens(tokens: Tokens): void {
  storage.set('access', tokens.access_token)
  storage.set('refresh', tokens.refresh_token)
  storage.set('accessExpires', String(tokens.access_expires_at))
  storage.set('refreshExpires', String(tokens.refresh_expires_at))
  storage.set('user', JSON.stringify(tokens.user))
}

async function parseError(response: Response): Promise<unknown> {
  try {
    const body = await response.json()
    return body?.detail ?? body?.error ?? body
  } catch {
    return (await response.text()) || response.statusText
  }
}

export async function refreshAccess(): Promise<boolean> {
  if (refreshPromise) return refreshPromise
  refreshPromise = (async () => {
    const refresh = storage.get('refresh')
    if (!refresh) return false
    try {
      const response = await fetch(endpoint('/api/auth/refresh'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh, device_name: navigator.userAgent.slice(0, 120) })
      })
      if (!response.ok) {
        storage.clearAuth()
        return false
      }
      saveTokens(await response.json() as Tokens)
      return true
    } catch {
      return false
    }
  })()
  try {
    return await refreshPromise
  } finally {
    refreshPromise = null
  }
}

export async function apiFetch<T = unknown>(
  path: string,
  init: RequestInit = {},
  options: { auth?: boolean; retry?: boolean } = {}
): Promise<T> {
  const auth = options.auth !== false
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (auth) {
    const access = storage.get('access')
    if (access) headers.set('Authorization', `Bearer ${access}`)
  }

  let response: Response
  try {
    response = await fetch(endpoint(path), { ...init, headers })
  } catch (error) {
    throw new ApiError(0, error instanceof Error ? error.message : 'Bridge is unreachable')
  }

  if (response.status === 401 && auth && options.retry !== false && await refreshAccess()) {
    return apiFetch<T>(path, init, { ...options, retry: false })
  }
  if (!response.ok) throw new ApiError(response.status, await parseError(response))
  if (response.status === 204) return undefined as T
  const contentType = response.headers.get('content-type') || ''
  return (contentType.includes('application/json') ? await response.json() : await response.text()) as T
}

export async function login(email: string, password: string): Promise<Tokens> {
  const tokens = await apiFetch<Tokens>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password, device_name: navigator.userAgent.slice(0, 120) })
  }, { auth: false })
  saveTokens(tokens)
  return tokens
}

export async function logout(): Promise<void> {
  const refresh = storage.get('refresh')
  try {
    await apiFetch('/api/auth/logout', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refresh || null })
    })
  } finally {
    storage.clearAuth()
  }
}

export function getStoredUser() {
  try {
    return JSON.parse(storage.get('user') || 'null')
  } catch {
    return null
  }
}

export function hasAccessToken(): boolean {
  return Boolean(storage.get('access'))
}

export function absoluteApiUrl(path: string): string {
  return endpoint(path)
}
