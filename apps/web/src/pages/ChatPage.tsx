import {
  AlertTriangle, Bot, Check, ChevronLeft, CircleStop, Clock3, GitBranch, Loader2,
  Menu, MessageSquarePlus, Network, Plus, RefreshCw, Send, Sparkles, Terminal,
  User, WandSparkles, X, Zap
} from 'lucide-react'
import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { Markdown } from '../components/Markdown'
import { Modal } from '../components/Modal'
import { Spinner } from '../components/Spinner'
import { useToast } from '../components/Toast'
import { useAuth } from '../context/AuthContext'
import { apiFetch } from '../lib/api'
import { listFromPayload, messageText, sessionId, sessionTitle, timestamp, truncate } from '../lib/format'
import { streamSse, type SseMessage } from '../lib/sse'
import type { HermesMessage, HermesSession, RunStatus, ToolEvent } from '../types'

interface ModelOption { id: string; label: string; provider?: string }
const TERMINAL = new Set(['completed', 'failed', 'cancelled', 'interrupted'])

function modelOptions(payload: unknown): ModelOption[] {
  const found = new Map<string, ModelOption>()
  const walk = (value: unknown, provider?: string) => {
    if (Array.isArray(value)) { value.forEach(item => walk(item, provider)); return }
    if (!value || typeof value !== 'object') return
    const record = value as Record<string, unknown>
    const nextProvider = String(record.provider || record.provider_name || provider || '') || undefined
    const id = record.id || record.model || record.value || record.model_id
    if (typeof id === 'string' && id && !found.has(id)) {
      found.set(id, { id, label: String(record.label || record.name || record.display_name || id), provider: nextProvider })
    }
    for (const [key, child] of Object.entries(record)) {
      if (['pricing', 'metadata', 'capabilities'].includes(key)) continue
      walk(child, nextProvider)
    }
  }
  walk(payload)
  return [...found.values()].slice(0, 500)
}

function recordOf(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

function runIdFrom(value: unknown): string {
  const record = recordOf(value)
  return String(record.run_id || record.id || '')
}

function sessionIdFrom(value: unknown): string {
  const record = recordOf(value)
  return String(record.session_id || record.stored_session_id || record.conversation_id || '')
}

function contentFromTerminal(data: Record<string, unknown>): string {
  if (typeof data.output === 'string') return data.output
  if (typeof data.text === 'string') return data.text
  const transcript = data.transcript || data.messages || data.turn
  if (Array.isArray(transcript)) {
    const assistants = transcript.filter(item => recordOf(item).role === 'assistant')
    const last = assistants.at(-1)
    if (last) return messageText(last as HermesMessage)
  }
  return ''
}

function storedRunKey(profile: string, session: string): string {
  return `hermes.companion.run.${profile}.${session}`
}

export function ChatPage() {
  const { activeProfile, setActiveProfile, profiles } = useAuth()
  const [params, setParams] = useSearchParams()
  const profileParam = params.get('profile')
  const sessionParam = params.get('session')
  const profile = profiles.find(item => item.slug === activeProfile)
  const [sessions, setSessions] = useState<HermesSession[]>([])
  const [selectedId, setSelectedId] = useState(sessionParam || '')
  const [messages, setMessages] = useState<HermesMessage[]>([])
  const [loadingSessions, setLoadingSessions] = useState(true)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [sessionDrawer, setSessionDrawer] = useState(false)
  const [draft, setDraft] = useState('')
  const [models, setModels] = useState<ModelOption[]>([])
  const [model, setModel] = useState('')
  const [running, setRunning] = useState(false)
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null)
  const [assistantDraft, setAssistantDraft] = useState('')
  const [timeline, setTimeline] = useState<ToolEvent[]>([])
  const [approval, setApproval] = useState<Record<string, unknown> | null>(null)
  const [steering, setSteering] = useState(false)
  const [steerText, setSteerText] = useState('')
  const [runError, setRunError] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const messageEndRef = useRef<HTMLDivElement | null>(null)
  const toast = useToast()

  useEffect(() => {
    if (profileParam && profiles.some(item => item.slug === profileParam && item.configured)) setActiveProfile(profileParam)
  }, [profileParam, profiles, setActiveProfile])

  useEffect(() => { messageEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages, assistantDraft, timeline.length])

  const loadSessions = useCallback(async () => {
    setLoadingSessions(true)
    try {
      const payload = await apiFetch(`/api/profiles/${activeProfile}/sessions?limit=200`)
      const items = listFromPayload<HermesSession>(payload, ['sessions', 'items', 'data'])
      setSessions(items)
      const requested = params.get('session')
      const candidate = requested && items.some(item => sessionId(item) === requested)
        ? requested : selectedId && items.some(item => sessionId(item) === selectedId)
          ? selectedId : items[0] ? sessionId(items[0]) : ''
      if (candidate && candidate !== selectedId) setSelectedId(candidate)
    } catch (error) { toast.push(error instanceof Error ? error.message : 'Unable to load sessions', 'error') }
    finally { setLoadingSessions(false) }
  }, [activeProfile, params, selectedId, toast])

  const loadMessages = useCallback(async (id: string) => {
    if (!id) { setMessages([]); return }
    setLoadingMessages(true)
    try {
      const payload = await apiFetch(`/api/profiles/${activeProfile}/sessions/${encodeURIComponent(id)}/messages`)
      setMessages(listFromPayload<HermesMessage>(payload, ['messages', 'items', 'data']))
    } catch (error) { toast.push(error instanceof Error ? error.message : 'Unable to load transcript', 'error') }
    finally { setLoadingMessages(false) }
  }, [activeProfile, toast])

  const loadModels = useCallback(async () => {
    try {
      const payload = await apiFetch(`/api/profiles/${activeProfile}/model-options`)
      const options = modelOptions(payload)
      setModels(options)
      if (model && !options.some(option => option.id === model)) setModel('')
    } catch { setModels([]) }
  }, [activeProfile, model])

  useEffect(() => { setSelectedId(''); setMessages([]); setRunStatus(null); setTimeline([]); setAssistantDraft(''); void loadSessions(); void loadModels() }, [activeProfile])
  useEffect(() => {
    if (!selectedId) return
    setParams(current => { const next = new URLSearchParams(current); next.set('profile', activeProfile); next.set('session', selectedId); return next }, { replace: true })
    void loadMessages(selectedId)
    setSessionDrawer(false)
  }, [selectedId, activeProfile, loadMessages, setParams])

  const handleEvent = useCallback((message: SseMessage) => {
    const data = recordOf(message.data)
    const event = String(data.event || message.type || 'message')
    if (event === 'assistant.delta') {
      const delta = data.delta ?? data.text
      if (typeof delta === 'string') setAssistantDraft(current => current + delta)
    } else if (event === 'approval.request') {
      setApproval(data); setRunStatus(current => current ? { ...current, status: 'waiting_for_approval', approval: data } : current)
    } else if (event.startsWith('tool.') || event.startsWith('subagent.') || event === 'reasoning.available' || event === 'run.steered') {
      setTimeline(current => [...current, { ...data, id: `${Date.now()}-${current.length}`, event } as ToolEvent])
    } else if (event.startsWith('run.')) {
      const status = event.slice(4)
      setRunStatus(current => ({ ...(current || { run_id: String(data.run_id || '') }), ...data, status } as RunStatus))
      if (TERMINAL.has(status)) {
        const authoritative = contentFromTerminal(data)
        if (authoritative) setAssistantDraft(authoritative)
        setRunning(false); setApproval(null)
      }
    }
  }, [])

  const followRun = useCallback(async (runId: string, session: string) => {
    abortRef.current?.abort()
    const controller = new AbortController(); abortRef.current = controller
    setRunning(true); setRunError('')
    let attempts = 0
    while (!controller.signal.aborted && attempts < 3) {
      try {
        await streamSse(`/api/profiles/${activeProfile}/runs/${encodeURIComponent(runId)}/events`, handleEvent, controller.signal)
        break
      } catch (error) {
        if (controller.signal.aborted) return
        attempts += 1
        try {
          const status = await apiFetch<RunStatus>(`/api/profiles/${activeProfile}/runs/${encodeURIComponent(runId)}`)
          setRunStatus(status)
          if (TERMINAL.has(status.status)) { setRunning(false); break }
        } catch { /* retry stream */ }
        if (attempts < 3) await new Promise(resolve => window.setTimeout(resolve, attempts * 1200))
        else setRunError(error instanceof Error ? error.message : 'Run stream disconnected')
      }
    }
    try {
      const status = await apiFetch<RunStatus>(`/api/profiles/${activeProfile}/runs/${encodeURIComponent(runId)}`)
      setRunStatus(status)
      if (TERMINAL.has(status.status)) {
        setRunning(false)
        const output = typeof status.output === 'string' ? status.output : ''
        if (output) setAssistantDraft(output)
      }
    } catch { /* terminal event already carried the result */ }
    if (!controller.signal.aborted) {
      localStorage.removeItem(storedRunKey(activeProfile, session))
      window.setTimeout(() => void loadMessages(session), 250)
    }
  }, [activeProfile, handleEvent, loadMessages])

  useEffect(() => {
    if (!selectedId) return
    const existing = localStorage.getItem(storedRunKey(activeProfile, selectedId))
    if (!existing) return
    void apiFetch<RunStatus>(`/api/profiles/${activeProfile}/runs/${encodeURIComponent(existing)}`)
      .then(status => {
        setRunStatus(status)
        if (!TERMINAL.has(status.status)) void followRun(existing, selectedId)
        else localStorage.removeItem(storedRunKey(activeProfile, selectedId))
      }).catch(() => localStorage.removeItem(storedRunKey(activeProfile, selectedId)))
    return () => abortRef.current?.abort()
  }, [selectedId, activeProfile])

  const createSession = async (): Promise<string> => {
    const result = await apiFetch<HermesSession>(`/api/profiles/${activeProfile}/sessions`, { method: 'POST', body: JSON.stringify({ title: 'New Companion session' }) })
    const id = sessionId(result)
    await loadSessions(); setSelectedId(id)
    return id
  }

  const submit = async () => {
    const input = draft.trim()
    if (!input || running || !profile?.permissions.chat) return
    let session = selectedId
    try {
      if (!session) session = await createSession()
      setDraft(''); setAssistantDraft(''); setTimeline([]); setApproval(null); setRunError('')
      setMessages(current => [...current, { role: 'user', content: input, created_at: Date.now() }])
      const payload: Record<string, unknown> = { input, session_id: session }
      if (model) payload.model = model
      const result = await apiFetch(`/api/profiles/${activeProfile}/runs`, { method: 'POST', body: JSON.stringify(payload) })
      const runId = runIdFrom(result)
      const returnedSession = sessionIdFrom(result)
      if (returnedSession && returnedSession !== session) { session = returnedSession; setSelectedId(returnedSession) }
      if (!runId) throw new Error('Hermes did not return a run ID')
      const status = { ...recordOf(result), run_id: runId, status: String(recordOf(result).status || 'queued') } as RunStatus
      setRunStatus(status); setRunning(true)
      localStorage.setItem(storedRunKey(activeProfile, session), runId)
      await followRun(runId, session)
    } catch (error) {
      setRunning(false); setRunError(error instanceof Error ? error.message : 'Unable to start run')
      toast.push(error instanceof Error ? error.message : 'Unable to start run', 'error')
    }
  }

  const onComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit() }
  }

  const stop = async () => {
    if (!runStatus?.run_id) return
    try {
      await apiFetch(`/api/profiles/${activeProfile}/runs/${encodeURIComponent(runStatus.run_id)}/stop`, { method: 'POST', body: '{}' })
      toast.push('Stop requested', 'info')
    } catch (error) { toast.push(error instanceof Error ? error.message : 'Stop failed', 'error') }
  }

  const sendSteer = async (event: FormEvent) => {
    event.preventDefault()
    if (!runStatus?.run_id || !steerText.trim()) return
    try {
      await apiFetch(`/api/profiles/${activeProfile}/runs/${encodeURIComponent(runStatus.run_id)}/steer`, { method: 'POST', body: JSON.stringify({ input: steerText.trim() }) })
      setSteering(false); setSteerText(''); toast.push('Guidance queued for the next tool boundary', 'success')
    } catch (error) { toast.push(error instanceof Error ? error.message : 'Steer failed', 'error') }
  }

  const resolveApproval = async (choice: 'once' | 'deny') => {
    if (!runStatus?.run_id) return
    try {
      await apiFetch(`/api/profiles/${activeProfile}/runs/${encodeURIComponent(runStatus.run_id)}/approval`, { method: 'POST', body: JSON.stringify({ choice }) })
      setApproval(null); toast.push(choice === 'once' ? 'Approved once' : 'Denied', choice === 'once' ? 'success' : 'info')
    } catch (error) { toast.push(error instanceof Error ? error.message : 'Approval failed', 'error') }
  }

  const selectedSession = sessions.find(session => sessionId(session) === selectedId)
  const statusLabel = runStatus?.status || (running ? 'running' : 'ready')
  const displayedMessages = useMemo(() => messages.filter(message => message.display_kind !== 'hidden'), [messages])

  return <div className="chat-page">
    <button className={`chat-drawer-scrim ${sessionDrawer ? 'show' : ''}`} onClick={() => setSessionDrawer(false)} aria-label="Close sessions" />
    <aside className={`chat-sessions ${sessionDrawer ? 'open' : ''}`}>
      <header><div><span className="eyebrow">{profile?.label}</span><h2>Sessions</h2></div><button className="icon-button mobile-only" onClick={() => setSessionDrawer(false)}><X size={18} /></button></header>
      <Button variant="primary" onClick={() => void createSession()} disabled={!profile?.permissions.session_write}><Plus size={15} /> New session</Button>
      <div className="chat-session-list">{loadingSessions ? <Spinner label="Loading" /> : sessions.map(session => {
        const id = sessionId(session)
        return <button key={id} className={id === selectedId ? 'active' : ''} onClick={() => setSelectedId(id)}><span className="session-glyph"><MessageSquarePlus size={16} /></span><span><strong>{sessionTitle(session)}</strong><small>{truncate(String(session.preview || timestamp(session.last_active || session.updated_at) || id), 62)}</small></span></button>
      })}</div>
    </aside>

    <section className="chat-workspace">
      <header className="chat-header">
        <button className="icon-button chat-menu-button" onClick={() => setSessionDrawer(true)}><Menu size={20} /></button>
        <div className="chat-title"><span className="agent-avatar small" style={{ '--profile-accent': profile?.accent } as CSSProperties}><Bot size={17} /></span><div><strong>{selectedSession ? sessionTitle(selectedSession) : profile?.label || 'Hermes'}</strong><small>{selectedId ? `${profile?.label} · ${selectedId.slice(0, 14)}…` : 'Create or select a session'}</small></div></div>
        <div className="chat-controls">
          <span className={`run-state state-${statusLabel}`}><span />{statusLabel.replaceAll('_', ' ')}</span>
          {models.length ? <select className="model-select" value={model} onChange={event => setModel(event.target.value)} title="Model override"><option value="">Profile default model</option>{models.map(option => <option key={option.id} value={option.id}>{option.provider ? `${option.provider} · ` : ''}{option.label}</option>)}</select> : null}
          <button className="icon-button" onClick={() => selectedId && void loadMessages(selectedId)} title="Refresh transcript"><RefreshCw size={17} /></button>
        </div>
      </header>

      <div className="chat-scroll">
        {!selectedId && !loadingSessions ? <EmptyState icon={MessageSquarePlus} title="Start a Hermes session" description="Create a durable conversation that remains available in Desktop, CLI and this companion." action={profile?.permissions.session_write ? <Button variant="primary" onClick={() => void createSession()}>Create session</Button> : undefined} /> : loadingMessages ? <div className="panel-loader"><Spinner label="Loading transcript" /></div> : <div className="message-column">
          {displayedMessages.map((message, index) => {
            const role = String(message.role || 'assistant')
            const text = messageText(message)
            if (!text && role !== 'tool') return null
            return <article className={`message message-${role}`} key={String(message.id || `${role}-${index}`)}><div className="message-avatar">{role === 'user' ? <User size={16} /> : role === 'tool' ? <Terminal size={16} /> : <Bot size={16} />}</div><div className="message-body"><header><strong>{role === 'user' ? 'You' : role === 'tool' ? 'Tool' : profile?.label || 'Hermes'}</strong><span>{timestamp(message.created_at)}</span></header><div className="message-content">{text ? <Markdown>{text}</Markdown> : <pre>{JSON.stringify(message.tool_calls, null, 2)}</pre>}</div></div></article>
          })}
          {(running || assistantDraft || timeline.length) ? <article className="message message-assistant live"><div className="message-avatar"><Bot size={16} /></div><div className="message-body"><header><strong>{profile?.label || 'Hermes'}</strong><span className="streaming-label">{running ? <><Loader2 size={13} className="spin" /> working</> : 'latest turn'}</span></header>{timeline.length ? <div className="tool-timeline">{timeline.map(item => <div className={`tool-event ${item.error ? 'error' : ''}`} key={item.id}><span>{item.event.startsWith('subagent') ? <Network size={14} /> : item.event === 'reasoning.available' ? <Sparkles size={14} /> : item.event === 'tool.completed' ? <Check size={14} /> : <Terminal size={14} />}</span><div><strong>{item.tool || item.event.replace('.', ' ')}</strong>{item.preview ? <small>{truncate(String(item.preview), 180)}</small> : null}</div>{typeof item.duration === 'number' ? <code>{item.duration}s</code> : null}</div>)}</div> : null}{assistantDraft ? <div className="message-content"><Markdown>{assistantDraft}</Markdown></div> : running ? <div className="thinking-row"><span /><span /><span /></div> : null}</div></article> : null}
          {approval ? <section className="approval-card"><header><span><AlertTriangle size={18} /></span><div><strong>Hermes needs approval</strong><p>{String(approval.description || approval.command || approval.preview || 'A gated tool action is waiting for your decision.')}</p></div></header>{approval.command ? <pre>{String(approval.command)}</pre> : null}<footer><Button variant="danger" onClick={() => void resolveApproval('deny')}>Deny</Button><Button variant="primary" onClick={() => void resolveApproval('once')}><Zap size={15} /> Approve once</Button></footer></section> : null}
          {runError ? <div className="banner banner-error"><AlertTriangle size={17} /><span>{runError}</span></div> : null}
          <div ref={messageEndRef} />
        </div>}
      </div>

      <footer className="composer-zone">
        {running ? <div className="run-toolbar"><span><Clock3 size={15} /> Run {runStatus?.run_id?.slice(0, 12)} is {statusLabel.replaceAll('_', ' ')}</span><div><Button size="sm" onClick={() => setSteering(true)} disabled={runStatus?.status !== 'running'}><WandSparkles size={14} /> Steer</Button><Button size="sm" variant="danger" onClick={() => void stop()}><CircleStop size={14} /> Stop</Button></div></div> : null}
        <div className="composer"><textarea rows={1} value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={onComposerKeyDown} placeholder={selectedId ? `Message ${profile?.label || 'Hermes'}…` : 'Create a session to begin…'} disabled={!selectedId && !profile?.permissions.session_write} /><button className="send-button" onClick={() => void submit()} disabled={!draft.trim() || running || !profile?.permissions.chat} aria-label="Send"><Send size={18} /></button></div>
        <small>Enter to send · Shift+Enter for a new line · tools and approvals execute through the selected Hermes profile</small>
      </footer>
    </section>

    {steering ? <Modal title="Steer the active run" onClose={() => setSteering(false)}><form className="stack-form" onSubmit={sendSteer}><p>Guidance is queued for the next Hermes tool boundary. It does not erase output already produced.</p><textarea rows={6} value={steerText} onChange={event => setSteerText(event.target.value)} autoFocus placeholder="Focus on the API boundary first; do not change the trading rules." /><div className="form-actions"><Button type="button" onClick={() => setSteering(false)}>Cancel</Button><Button type="submit" variant="primary" disabled={!steerText.trim()}>Queue guidance</Button></div></form></Modal> : null}
  </div>
}
