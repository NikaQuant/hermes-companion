import { CalendarClock, Clock3, Pause, Play, Plus, RefreshCw, RotateCw, Trash2 } from 'lucide-react'
import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { Spinner } from '../components/Spinner'
import { useToast } from '../components/Toast'
import { useAuth } from '../context/AuthContext'
import { apiFetch } from '../lib/api'
import { listFromPayload, timestamp } from '../lib/format'
import type { Job } from '../types'

function jobId(job: Job): string { return String(job.id || job.job_id || '') }
function isPaused(job: Job): boolean { return job.paused === true || job.enabled === false || job.status === 'paused' }

export function AutomationsPage() {
  const { activeProfile, profiles } = useAuth()
  const profile = profiles.find(item => item.slug === activeProfile)
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<Job | null>(null)
  const [busyId, setBusyId] = useState('')
  const toast = useToast()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const payload = await apiFetch(`/api/profiles/${activeProfile}/jobs`)
      setJobs(listFromPayload<Job>(payload, ['jobs', 'items', 'data']))
    } catch (error) { toast.push(error instanceof Error ? error.message : 'Unable to load jobs', 'error') }
    finally { setLoading(false) }
  }, [activeProfile, toast])

  useEffect(() => { void load() }, [load])
  const active = useMemo(() => jobs.filter(job => !isPaused(job)).length, [jobs])

  const action = async (job: Job, name: 'run' | 'pause' | 'resume') => {
    const id = jobId(job); setBusyId(id)
    try {
      await apiFetch(`/api/profiles/${activeProfile}/jobs/${encodeURIComponent(id)}/${name}`, { method: 'POST', body: '{}' })
      toast.push(name === 'run' ? 'Job marked to run' : `Job ${name}d`, 'success')
      await load()
    } catch (error) { toast.push(error instanceof Error ? error.message : `Job ${name} failed`, 'error') }
    finally { setBusyId('') }
  }

  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const body = {
      name: String(data.get('name') || '').trim(),
      prompt: String(data.get('prompt') || '').trim(),
      schedule: String(data.get('schedule') || '').trim(),
      enabled: true
    }
    setBusyId('creating')
    try {
      await apiFetch(`/api/profiles/${activeProfile}/jobs`, { method: 'POST', body: JSON.stringify(body) })
      setCreating(false); toast.push('Automation created', 'success'); await load()
    } catch (error) { toast.push(error instanceof Error ? error.message : 'Create failed', 'error') }
    finally { setBusyId('') }
  }

  const remove = async () => {
    if (!deleting) return
    const id = jobId(deleting); setBusyId(id)
    try {
      await apiFetch(`/api/profiles/${activeProfile}/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' })
      setDeleting(null); toast.push('Automation deleted', 'success'); await load()
    } catch (error) { toast.push(error instanceof Error ? error.message : 'Delete failed', 'error') }
    finally { setBusyId('') }
  }

  return <div className="page">
    <PageHeader eyebrow={profile?.label.toUpperCase()} title="Automations" description="Hermes gateway jobs for the selected profile. Schedules run in the gateway host’s local timezone." actions={<div className="page-action-group"><Button onClick={() => void load()}><RefreshCw size={15} /> Refresh</Button>{profile?.permissions.jobs_write ? <Button variant="primary" onClick={() => setCreating(true)}><Plus size={15} /> New job</Button> : null}</div>} />
    <section className="automation-summary"><div><span><CalendarClock /></span><div><small>Total jobs</small><strong>{jobs.length}</strong></div></div><div><span><Play /></span><div><small>Active</small><strong>{active}</strong></div></div><div><span><Pause /></span><div><small>Paused</small><strong>{jobs.length - active}</strong></div></div></section>
    {!profile?.permissions.jobs_write ? <div className="banner banner-warn"><Clock3 size={18} /><span>This profile’s remote job mutations are disabled by bridge policy. Existing jobs remain visible.</span></div> : null}

    {loading ? <div className="panel-loader"><Spinner label="Loading automations" /></div> : jobs.length ? <div className="job-grid">{jobs.map(job => {
      const id = jobId(job); const paused = isPaused(job); const busy = busyId === id
      return <article className="job-card" key={id}><header><span className={`job-state ${paused ? 'paused' : 'active'}`}><span />{paused ? 'Paused' : 'Active'}</span><code>{id.slice(0, 12)}</code></header><h3>{String(job.name || 'Unnamed automation')}</h3><p>{String(job.prompt || job.description || 'No prompt preview available.')}</p><div className="job-details"><div><Clock3 size={14} /><span>{String(job.schedule || 'Schedule not reported')}</span></div><div><RotateCw size={14} /><span>Next: {timestamp(job.next_run_at) || 'not scheduled'}</span></div></div><footer>{profile?.permissions.jobs_write ? <><Button size="sm" disabled={busy} onClick={() => void action(job, 'run')}><Play size={14} /> Run now</Button><Button size="sm" disabled={busy} onClick={() => void action(job, paused ? 'resume' : 'pause')}>{paused ? <Play size={14} /> : <Pause size={14} />}{paused ? 'Resume' : 'Pause'}</Button><button className="icon-button danger" title="Delete" onClick={() => setDeleting(job)}><Trash2 size={16} /></button></> : <span className="read-only-label">Read only</span>}</footer></article>
    })}</div> : <EmptyState icon={CalendarClock} title="No automations" description={profile?.permissions.jobs_write ? 'Create a gateway-backed routine for this profile.' : 'No jobs were returned for this profile.'} action={profile?.permissions.jobs_write ? <Button variant="primary" onClick={() => setCreating(true)}>Create job</Button> : undefined} />}

    {creating ? <Modal title="Create Hermes automation" onClose={() => setCreating(false)}>
      <form className="stack-form" onSubmit={create}><label><span>Name</span><input name="name" required autoFocus placeholder="Daily Hermes release study" /></label><label><span>Schedule</span><input name="schedule" required placeholder="0 9 * * *  or  every 6h" /><small>Use a Hermes-supported five-field cron or interval expression.</small></label><label><span>Prompt</span><textarea name="prompt" rows={8} required placeholder="Read current official Hermes releases, save useful findings to the project, and report only material changes." /></label><div className="form-actions"><Button type="button" onClick={() => setCreating(false)}>Cancel</Button><Button type="submit" variant="primary" disabled={busyId === 'creating'}>{busyId === 'creating' ? 'Creating…' : 'Create automation'}</Button></div></form>
    </Modal> : null}

    {deleting ? <Modal title="Delete automation?" onClose={() => setDeleting(null)} footer={<><Button onClick={() => setDeleting(null)}>Cancel</Button><Button variant="danger" disabled={Boolean(busyId)} onClick={() => void remove()}>Delete</Button></>}><p>This permanently removes <strong>{String(deleting.name || jobId(deleting))}</strong> from Hermes.</p></Modal> : null}
  </div>
}
