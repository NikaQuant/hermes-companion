import { ArrowRight, LockKeyhole, Server, ShieldCheck, Smartphone } from 'lucide-react'
import { FormEvent, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { ApiError } from '../lib/api'

export function LoginPage() {
  const { login, bridgeUrl } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [endpoint, setEndpoint] = useState(bridgeUrl)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      await login(email.trim(), password, endpoint)
    } catch (caught) {
      const message = caught instanceof ApiError
        ? (typeof caught.detail === 'string' ? caught.detail : caught.message)
        : caught instanceof Error ? caught.message : 'Login failed'
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-intro">
        <div className="brand login-brand"><span className="brand-mark">H</span><span className="brand-copy"><strong>Hermes</strong><small>Companion</small></span></div>
        <div className="login-copy">
          <div className="eyebrow">YOUR HERMES, EVERYWHERE</div>
          <h1>One control surface.<br /><span>Every approved agent.</span></h1>
          <p>Continue Desktop sessions, monitor durable runs, review tool activity, resolve approvals and manage automations from web, Windows or Android.</p>
        </div>
        <div className="login-features">
          <div><ShieldCheck /><span><strong>Profile isolated</strong><small>Safety World is structurally excluded.</small></span></div>
          <div><Smartphone /><span><strong>Cross-device sessions</strong><small>Resume the same durable Hermes transcript.</small></span></div>
          <div><LockKeyhole /><span><strong>Keys stay server-side</strong><small>The app never receives Hermes API secrets.</small></span></div>
        </div>
      </section>
      <section className="login-panel">
        <form className="login-card" onSubmit={submit}>
          <header>
            <span className="login-lock"><LockKeyhole size={21} /></span>
            <div><h2>Operator sign in</h2><p>Authenticate to your private bridge.</p></div>
          </header>
          <label>
            <span>Email</span>
            <input type="email" autoComplete="username" value={email} onChange={event => setEmail(event.target.value)} placeholder="nik@example.com" required />
          </label>
          <label>
            <span>Password</span>
            <input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} placeholder="••••••••••••" required />
          </label>
          <label>
            <span>Bridge endpoint</span>
            <div className="input-icon"><Server size={16} /><input value={endpoint} onChange={event => setEndpoint(event.target.value)} placeholder="Same origin, or https://app.example.com" /></div>
            <small>Leave blank when the bridge serves this web app. Native apps require the HTTPS address.</small>
          </label>
          {error ? <div className="form-error">{error}</div> : null}
          <button className="login-submit" disabled={busy}>{busy ? 'Authenticating…' : 'Open Companion'}<ArrowRight size={18} /></button>
          <footer><ShieldCheck size={14} /> Hermes credentials are never stored in this client.</footer>
        </form>
      </section>
    </main>
  )
}
