import {
  Activity, AlertTriangle, ArrowRight, Bot, CalendarClock, CheckCircle2, CircleOff,
  MessageSquareText, RefreshCw, ShieldCheck, Workflow
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../components/Button'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { apiFetch } from '../lib/api'
import type { HermesProfile } from '../types'

interface Probe { profile: string; online: boolean; health?: unknown; error?: string }
interface Overview { bridge: { online: boolean; environment: string }; profiles: HermesProfile[]; statuses: Probe[] }

export function CommandCenterPage() {
  const { profiles, activeProfile } = useAuth()
  const [overview, setOverview] = useState<Overview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try { setOverview(await apiFetch<Overview>('/api/overview')) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to load overview') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { void load() }, [load])
  const configured = profiles.filter(profile => profile.configured)
  const online = overview?.statuses.filter(item => item.online).length || 0
  const selected = profiles.find(profile => profile.slug === activeProfile)

  return (
    <div className="page command-page">
      <PageHeader
        eyebrow="HERMES UNIVERSE"
        title="Command Center"
        description="Operational view of your regular Hermes profiles, durable work and remote control surface."
        actions={<Button onClick={() => void load()} disabled={loading}><RefreshCw size={15} className={loading ? 'spin' : ''} /> Refresh</Button>}
      />

      {error ? <div className="banner banner-error"><AlertTriangle size={18} /><span>{error}</span></div> : null}

      <section className="metric-grid">
        <article className="metric-card"><div className="metric-icon violet"><Activity /></div><div><small>Bridge</small><strong>{overview?.bridge.online ? 'Online' : loading ? 'Checking' : 'Offline'}</strong><span>{overview?.bridge.environment || '—'}</span></div></article>
        <article className="metric-card"><div className="metric-icon cyan"><Bot /></div><div><small>Profiles online</small><strong>{online} / {configured.length}</strong><span>Approved regular profiles</span></div></article>
        <article className="metric-card"><div className="metric-icon green"><ShieldCheck /></div><div><small>Isolation</small><strong>Enforced</strong><span>Safety profiles hard-blocked</span></div></article>
        <article className="metric-card"><div className="metric-icon amber"><Workflow /></div><div><small>Active agent</small><strong>{selected?.label || '—'}</strong><span>{selected?.slug || 'No profile selected'}</span></div></article>
      </section>

      <section className="section-block">
        <div className="section-heading"><div><span className="eyebrow">AGENT FLEET</span><h2>Approved profiles</h2></div><span className="section-note">Only profiles with a configured server-side key can be selected.</span></div>
        <div className="profile-grid">
          {profiles.map(profile => {
            const status = overview?.statuses.find(item => item.profile === profile.slug)
            const disabled = !profile.configured
            return (
              <article className={`profile-card ${disabled ? 'disabled' : ''}`} key={profile.slug} style={{ '--profile-accent': profile.accent } as CSSProperties}>
                <header><span className="agent-avatar"><Bot size={21} /></span><StatusPill status={disabled ? 'neutral' : status?.online ? 'online' : status ? 'offline' : 'warn'}>{disabled ? 'Not configured' : status?.online ? 'Online' : status ? 'Offline' : 'Checking'}</StatusPill></header>
                <h3>{profile.label}</h3><code>{profile.slug}</code><p>{profile.description}</p>
                <footer>
                  <div className="permission-dots" title="Enabled remote capabilities">
                    {Object.entries(profile.permissions).map(([name, enabled]) => <span key={name} className={enabled ? 'enabled' : ''}>{name.replace('_', ' ')}</span>)}
                  </div>
                  {disabled ? <CircleOff size={17} /> : <Link to={`/chat?profile=${profile.slug}`} aria-label={`Open ${profile.label}`}><ArrowRight size={18} /></Link>}
                </footer>
              </article>
            )
          })}
        </div>
      </section>

      <section className="quick-grid">
        <Link to="/chat" className="quick-card"><span><MessageSquareText /></span><div><h3>Continue a session</h3><p>Chat through durable runs with tool events, steering, stop and explicit approvals.</p></div><ArrowRight /></Link>
        <Link to="/automations" className="quick-card"><span><CalendarClock /></span><div><h3>Review automations</h3><p>Inspect jobs, run approved routines now and manage schedules by profile.</p></div><ArrowRight /></Link>
        <Link to="/audit" className="quick-card"><span><CheckCircle2 /></span><div><h3>Inspect audit trail</h3><p>See sign-ins, run controls, approvals, session changes and job mutations.</p></div><ArrowRight /></Link>
      </section>
    </div>
  )
}
