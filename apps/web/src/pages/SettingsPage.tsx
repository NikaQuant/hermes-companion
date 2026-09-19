import { Download, ExternalLink, KeyRound, MonitorSmartphone, Save, Server, ShieldOff } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { Button } from '../components/Button'
import { PageHeader } from '../components/PageHeader'
import { useToast } from '../components/Toast'
import { useAuth } from '../context/AuthContext'

interface InstallPromptEvent extends Event { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> }

export function SettingsPage() {
  const { bridgeUrl, setBridgeUrl, profiles, reloadProfiles } = useAuth()
  const [value, setValue] = useState(bridgeUrl)
  const [installPrompt, setInstallPrompt] = useState<InstallPromptEvent | null>(null)
  const toast = useToast()

  useEffect(() => {
    const handler = (event: Event) => { event.preventDefault(); setInstallPrompt(event as InstallPromptEvent) }
    window.addEventListener('beforeinstallprompt', handler)
    return () => window.removeEventListener('beforeinstallprompt', handler)
  }, [])

  const save = async (event: FormEvent) => {
    event.preventDefault()
    try {
      setBridgeUrl(value)
      await reloadProfiles()
      toast.push('Bridge endpoint saved', 'success')
    } catch (error) { toast.push(error instanceof Error ? error.message : 'Invalid bridge URL', 'error') }
  }

  return <div className="page">
    <PageHeader eyebrow="CLIENT CONFIGURATION" title="Settings" description="Configure this client surface. Hermes secrets remain in the bridge environment." />
    <div className="settings-grid">
      <section className="settings-card wide"><header><span><Server /></span><div><h2>Bridge endpoint</h2><p>Web uses same-origin by default. Android and Windows wrappers need the public HTTPS endpoint.</p></div></header><form onSubmit={save} className="endpoint-form"><input value={value} onChange={event => setValue(event.target.value)} placeholder="https://app.nikaquant.com or blank for same origin" /><Button variant="primary" type="submit"><Save size={15} /> Save and reconnect</Button></form><small>Never point the client directly at Hermes port 8642. The bridge must remain between the device and Hermes.</small></section>
      <section className="settings-card"><header><span><MonitorSmartphone /></span><div><h2>Install this app</h2><p>Use the same interface as a standalone PWA on desktop or Android.</p></div></header><Button disabled={!installPrompt} onClick={() => void installPrompt?.prompt()}><Download size={15} /> {installPrompt ? 'Install PWA' : 'Already installed or unavailable'}</Button></section>
      <section className="settings-card"><header><span><KeyRound /></span><div><h2>Credential model</h2><p>Short-lived opaque access tokens with rotating refresh tokens. Passwords use scrypt.</p></div></header><div className="settings-value">Hermes profile keys: <strong>server only</strong></div></section>
      <section className="settings-card danger-zone"><header><span><ShieldOff /></span><div><h2>Safety World boundary</h2><p>Live Safe, Live Judge, HermesSafety and Safety World aliases are hard-blocked.</p></div></header><div className="settings-value">Remote exposure: <strong>not permitted</strong></div></section>
    </div>
    <section className="section-block"><div className="section-heading"><div><span className="eyebrow">PROFILE INVENTORY</span><h2>Configured bridge routes</h2></div></div><div className="settings-profile-list">{profiles.map(profile => <article key={profile.slug}><span className="agent-color" style={{ background: profile.accent }} /><div><strong>{profile.label}</strong><code>{profile.slug}</code></div><span className={profile.configured ? 'configured' : 'missing'}>{profile.configured ? 'Key configured' : 'Missing key'}</span></article>)}</div></section>
    <section className="about-card"><div className="brand"><span className="brand-mark">H</span><span className="brand-copy"><strong>Hermes Companion</strong><small>v0.3.0</small></span></div><p>Independent operator interface built on Hermes Agent’s authenticated API surfaces.</p><a href="/api/health" target="_blank" rel="noreferrer">Bridge health <ExternalLink size={13} /></a></section>
  </div>
}
