import { Copy, ExternalLink, GitFork, MessageSquarePlus, Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { Spinner } from '../components/Spinner'
import { useToast } from '../components/Toast'
import { useAuth } from '../context/AuthContext'
import { apiFetch } from '../lib/api'
import { listFromPayload, sessionId, sessionTitle, timestamp } from '../lib/format'
import type { HermesSession } from '../types'

export function SessionsPage() {
  const { activeProfile, profiles } = useAuth()
  const profile = profiles.find(item => item.slug === activeProfile)
  const [sessions, setSessions] = useState<HermesSession[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [creating, setCreating] = useState(false)
  const [rename, setRename] = useState<HermesSession | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [deleting, setDeleting] = useState<HermesSession | null>(null)
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()
  const toast = useToast()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const payload = await apiFetch(`/api/profiles/${activeProfile}/sessions?limit=200`)
      setSessions(listFromPayload<HermesSession>(payload, ['sessions', 'items', 'data']))
    } catch (error) {
      toast.push(error instanceof Error ? error.message : 'Unable to load sessions', 'error')
    } finally { setLoading(false) }
  }, [activeProfile, toast])

  useEffect(() => { void load() }, [load])
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return sessions.filter(session => !needle || `${sessionTitle(session)} ${sessionId(session)} ${session.preview || ''}`.toLowerCase().includes(needle))
  }, [sessions, query])

  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const title = String(form.get('title') || '').trim()
    setBusy(true)
    try {
      const result = await apiFetch<HermesSession>(`/api/profiles/${activeProfile}/sessions`, {
        method: 'POST', body: JSON.stringify(title ? { title } : {})
      })
      setCreating(false)
      await load()
      const id = sessionId(result)
      if (id) navigate(`/chat?profile=${activeProfile}&session=${encodeURIComponent(id)}`)
      toast.push('Session created', 'success')
    } catch (error) { toast.push(error instanceof Error ? error.message : 'Create failed', 'error') }
    finally { setBusy(false) }
  }

  const saveRename = async () => {
    if (!rename) return
    setBusy(true)
    try {
      await apiFetch(`/api/profiles/${activeProfile}/sessions/${encodeURIComponent(sessionId(rename))}`, {
        method: 'PATCH', body: JSON.stringify({ title: renameValue.trim() })
      })
      setRename(null); await load(); toast.push('Session renamed', 'success')
    } catch (error) { toast.push(error instanceof Error ? error.message : 'Rename failed', 'error') }
    finally { setBusy(false) }
  }

  const fork = async (session: HermesSession) => {
    setBusy(true)
    try {
      const result = await apiFetch<HermesSession>(`/api/profiles/${activeProfile}/sessions/${encodeURIComponent(sessionId(session))}/fork`, { method: 'POST', body: '{}' })
      await load()
      const id = sessionId(result)
      if (id) navigate(`/chat?profile=${activeProfile}&session=${encodeURIComponent(id)}`)
      toast.push('Session branch created', 'success')
    } catch (error) { toast.push(error instanceof Error ? error.message : 'Fork failed', 'error') }
    finally { setBusy(false) }
  }

  const remove = async () => {
    if (!deleting) return
    setBusy(true)
    try {
      await apiFetch(`/api/profiles/${activeProfile}/sessions/${encodeURIComponent(sessionId(deleting))}`, { method: 'DELETE' })
      setDeleting(null); await load(); toast.push('Session deleted', 'success')
    } catch (error) { toast.push(error instanceof Error ? error.message : 'Delete failed', 'error') }
    finally { setBusy(false) }
  }

  return (
    <div className="page">
      <PageHeader eyebrow={profile?.label.toUpperCase()} title="Sessions" description="Durable Hermes transcripts shared with Desktop, CLI and this companion." actions={
        profile?.permissions.session_write ? <Button variant="primary" onClick={() => setCreating(true)}><Plus size={16} /> New session</Button> : null
      } />
      <div className="toolbar-row">
        <label className="search-box"><Search size={16} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search title, preview or ID" /></label>
        <Button onClick={() => void load()}>Refresh</Button>
      </div>

      {loading ? <div className="panel-loader"><Spinner label="Loading sessions" /></div> : filtered.length ? (
        <div className="session-table-wrap">
          <table className="session-table">
            <thead><tr><th>Session</th><th>Last activity</th><th>ID</th><th aria-label="Actions" /></tr></thead>
            <tbody>{filtered.map(session => {
              const id = sessionId(session)
              return <tr key={id}>
                <td><button className="session-title-button" onClick={() => navigate(`/chat?profile=${activeProfile}&session=${encodeURIComponent(id)}`)}><strong>{sessionTitle(session)}</strong><small>{String(session.preview || 'Open transcript')}</small></button></td>
                <td>{timestamp(session.last_active || session.updated_at || session.created_at) || '—'}</td>
                <td><code>{id.slice(0, 18)}{id.length > 18 ? '…' : ''}</code><button className="inline-copy" onClick={() => void navigator.clipboard.writeText(id)}><Copy size={13} /></button></td>
                <td><div className="table-actions">
                  <button title="Open chat" onClick={() => navigate(`/chat?profile=${activeProfile}&session=${encodeURIComponent(id)}`)}><ExternalLink /></button>
                  {profile?.permissions.session_write ? <>
                    <button title="Rename" onClick={() => { setRename(session); setRenameValue(sessionTitle(session)) }}><Pencil /></button>
                    <button title="Branch" disabled={busy} onClick={() => void fork(session)}><GitFork /></button>
                    <button title="Delete" className="danger" onClick={() => setDeleting(session)}><Trash2 /></button>
                  </> : null}
                </div></td>
              </tr>
            })}</tbody>
          </table>
        </div>
      ) : <EmptyState icon={MessageSquarePlus} title="No matching sessions" description={query ? 'Change the search query.' : 'Create the first durable session for this profile.'} action={profile?.permissions.session_write ? <Button variant="primary" onClick={() => setCreating(true)}>Create session</Button> : undefined} />}

      {creating ? <Modal title="Create Hermes session" onClose={() => setCreating(false)} footer={null}>
        <form className="stack-form" onSubmit={create}><label><span>Title</span><input name="title" autoFocus placeholder="Research, build or coordination task" /></label><div className="form-actions"><Button type="button" onClick={() => setCreating(false)}>Cancel</Button><Button type="submit" variant="primary" disabled={busy}>{busy ? 'Creating…' : 'Create and open'}</Button></div></form>
      </Modal> : null}

      {rename ? <Modal title="Rename session" onClose={() => setRename(null)} footer={<><Button onClick={() => setRename(null)}>Cancel</Button><Button variant="primary" disabled={busy || !renameValue.trim()} onClick={() => void saveRename()}>Save</Button></>}>
        <label className="field"><span>Title</span><input autoFocus value={renameValue} onChange={event => setRenameValue(event.target.value)} /></label>
      </Modal> : null}

      {deleting ? <Modal title="Delete session?" onClose={() => setDeleting(null)} footer={<><Button onClick={() => setDeleting(null)}>Cancel</Button><Button variant="danger" disabled={busy} onClick={() => void remove()}>{busy ? 'Deleting…' : 'Delete permanently'}</Button></>}>
        <p>This removes <strong>{sessionTitle(deleting)}</strong> from the selected Hermes profile. The operation cannot be undone.</p>
      </Modal> : null}
    </div>
  )
}
