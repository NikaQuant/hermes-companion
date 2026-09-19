import { useEffect } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { Shell } from './components/Shell'
import { Spinner } from './components/Spinner'
import { ToastProvider } from './components/Toast'
import { useAuth } from './context/AuthContext'
import { apiFetch } from './lib/api'
import { AuditPage } from './pages/AuditPage'
import { AutomationsPage } from './pages/AutomationsPage'
import { ChatPage } from './pages/ChatPage'
import { CommandCenterPage } from './pages/CommandCenterPage'
import { LoginPage } from './pages/LoginPage'
import { SessionsPage } from './pages/SessionsPage'
import { SettingsPage } from './pages/SettingsPage'

function HandoffResolver() {
  const { user, setActiveProfile } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (!user) return
    const params = new URLSearchParams(window.location.search)
    const directProfile = params.get('profile')
    const directSession = params.get('session')
    const token = params.get('handoff')

    const go = (profile: string, sessionId: string) => {
      setActiveProfile(profile)
      params.delete('profile'); params.delete('session'); params.delete('handoff')
      window.history.replaceState({}, '', `${window.location.pathname}${params.size ? `?${params}` : ''}`)
      navigate(`/chat?profile=${encodeURIComponent(profile)}&session=${encodeURIComponent(sessionId)}`, { replace: true })
    }

    if (directProfile && directSession) {
      go(directProfile, directSession)
    } else if (token) {
      apiFetch<{ profile: string; session_id: string }>(`/api/handoff/${encodeURIComponent(token)}`)
        .then(result => go(result.profile, result.session_id))
        .catch(() => undefined)
    }
  }, [user, navigate, setActiveProfile])
  return null
}

export function App() {
  const { user, loading } = useAuth()
  if (loading) return <div className="full-loader"><div className="brand"><span className="brand-mark">H</span><strong>Hermes Companion</strong></div><Spinner label="Connecting to bridge" /></div>
  if (!user) return <LoginPage />

  return (
    <ToastProvider>
      <HandoffResolver />
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<CommandCenterPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="sessions" element={<SessionsPage />} />
          <Route path="automations" element={<AutomationsPage />} />
          <Route path="audit" element={<AuditPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </ToastProvider>
  )
}
