import { ClipboardCheck, RefreshCw, ShieldCheck } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { Spinner } from '../components/Spinner'
import { useToast } from '../components/Toast'
import { apiFetch } from '../lib/api'
import { timestamp } from '../lib/format'

interface AuditEvent {
  id: number
  event: string
  profile?: string
  email?: string
  ip?: string
  created_at: number
  metadata?: Record<string, unknown>
}

export function AuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [loading, setLoading] = useState(true)
  const toast = useToast()
  const load = useCallback(async () => {
    setLoading(true)
    try { setEvents((await apiFetch<{ events: AuditEvent[] }>('/api/audit?limit=250')).events) }
    catch (error) { toast.push(error instanceof Error ? error.message : 'Audit load failed', 'error') }
    finally { setLoading(false) }
  }, [toast])
  useEffect(() => { void load() }, [load])

  return <div className="page">
    <PageHeader eyebrow="CONTROL PLANE" title="Audit trail" description="Bridge-side record of security-sensitive operator actions. Hermes remains authoritative for agent and tool logs." actions={<Button onClick={() => void load()}><RefreshCw size={15} /> Refresh</Button>} />
    <div className="banner banner-info"><ShieldCheck size={18} /><span>Hermes API keys and password material are never written to this log.</span></div>
    {loading ? <div className="panel-loader"><Spinner label="Loading audit events" /></div> : events.length ? <div className="audit-list">
      {events.map(event => <article key={event.id} className="audit-row"><span className="audit-icon"><ClipboardCheck size={17} /></span><div className="audit-main"><strong>{event.event}</strong><p>{Object.entries(event.metadata || {}).map(([key, value]) => `${key}=${typeof value === 'object' ? JSON.stringify(value) : String(value)}`).join(' · ') || 'No additional metadata'}</p></div><div className="audit-meta"><code>{event.profile || 'bridge'}</code><span>{event.email || 'system'} · {timestamp(event.created_at)}</span></div></article>)}
    </div> : <EmptyState icon={ClipboardCheck} title="No audit events" description="Security-sensitive activity will appear here." />}
  </div>
}
