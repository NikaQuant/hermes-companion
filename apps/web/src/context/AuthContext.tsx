import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { apiFetch, getStoredUser, hasAccessToken, login as apiLogin, logout as apiLogout } from '../lib/api'
import { normalizedBridgeUrl, storage } from '../lib/storage'
import type { HermesProfile, User } from '../types'

interface AuthValue {
  user: User | null
  profiles: HermesProfile[]
  loading: boolean
  bridgeUrl: string
  activeProfile: string
  login: (email: string, password: string, bridgeUrl: string) => Promise<void>
  logout: () => Promise<void>
  reloadProfiles: () => Promise<void>
  setActiveProfile: (profile: string) => void
  setBridgeUrl: (url: string) => void
}

const AuthContext = createContext<AuthValue | null>(null)

function defaultBridgeUrl(): string {
  const saved = storage.get('bridgeUrl')
  if (saved) return saved
  if (['http:', 'https:'].includes(window.location.protocol)) return ''
  return ''
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => getStoredUser())
  const [profiles, setProfiles] = useState<HermesProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [bridgeUrl, setBridgeUrlState] = useState(defaultBridgeUrl)
  const [activeProfile, setActiveProfileState] = useState(() => storage.get('profile') || 'default')

  const setBridgeUrl = useCallback((url: string) => {
    const normalized = normalizedBridgeUrl(url)
    storage.set('bridgeUrl', normalized)
    setBridgeUrlState(normalized)
  }, [])

  const reloadProfiles = useCallback(async () => {
    const response = await apiFetch<{ profiles: HermesProfile[] }>('/api/profiles')
    setProfiles(response.profiles)
    const configured = response.profiles.filter(profile => profile.configured)
    if (!configured.some(profile => profile.slug === activeProfile) && configured[0]) {
      storage.set('profile', configured[0].slug)
      setActiveProfileState(configured[0].slug)
    }
  }, [activeProfile])

  useEffect(() => {
    let cancelled = false
    const initialise = async () => {
      if (!hasAccessToken()) {
        if (!cancelled) setLoading(false)
        return
      }
      try {
        const me = await apiFetch<User>('/api/auth/me')
        if (cancelled) return
        setUser(me)
        await reloadProfiles()
      } catch {
        storage.clearAuth()
        if (!cancelled) setUser(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void initialise()
    return () => { cancelled = true }
  }, []) // bridge/profile changes are handled explicitly

  const login = useCallback(async (email: string, password: string, url: string) => {
    setBridgeUrl(url)
    const tokens = await apiLogin(email, password)
    setUser(tokens.user)
    await reloadProfiles()
  }, [reloadProfiles, setBridgeUrl])

  const logout = useCallback(async () => {
    try { await apiLogout() } finally {
      setUser(null)
      setProfiles([])
    }
  }, [])

  const setActiveProfile = useCallback((profile: string) => {
    const candidate = profiles.find(item => item.slug === profile && item.configured)
    if (!candidate) return
    storage.set('profile', profile)
    setActiveProfileState(profile)
  }, [profiles])

  const value = useMemo<AuthValue>(() => ({
    user, profiles, loading, bridgeUrl, activeProfile, login, logout,
    reloadProfiles, setActiveProfile, setBridgeUrl
  }), [
    user, profiles, loading, bridgeUrl, activeProfile, login, logout,
    reloadProfiles, setActiveProfile, setBridgeUrl
  ])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
