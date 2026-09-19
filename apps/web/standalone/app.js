const VERSION = '0.3.2'
const BUILD = 'dev'
const VERSION_LABEL = `v${VERSION} · ${BUILD}`
const ROOT = document.getElementById('root')
const STORAGE_PREFIX = 'hermes.companion.'

function deviceId() {
  let value = localStorage.getItem(STORAGE_PREFIX + 'deviceId')
  if (!value) {
    value = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`
    localStorage.setItem(STORAGE_PREFIX + 'deviceId', value)
  }
  return value
}

const storage = {
  get(key) {
    if (key === 'access' || key === 'accessExpires') {
      const current = sessionStorage.getItem(STORAGE_PREFIX + key)
      if (current) return current
      const legacy = localStorage.getItem(STORAGE_PREFIX + key)
      if (legacy) {
        sessionStorage.setItem(STORAGE_PREFIX + key, legacy)
        localStorage.removeItem(STORAGE_PREFIX + key)
      }
      return legacy
    }
    return localStorage.getItem(STORAGE_PREFIX + key)
  },
  set(key, value) {
    const target = key === 'access' || key === 'accessExpires' ? sessionStorage : localStorage
    target.setItem(STORAGE_PREFIX + key, String(value))
  },
  remove(key) {
    localStorage.removeItem(STORAGE_PREFIX + key)
    sessionStorage.removeItem(STORAGE_PREFIX + key)
  },
  json(key, fallback = null) {
    try { return JSON.parse(this.get(key) || 'null') ?? fallback } catch { return fallback }
  },
  setJson(key, value) { this.set(key, JSON.stringify(value)) },
  clearAuth() {
    for (const key of ['access', 'refresh', 'accessExpires', 'refreshExpires', 'user']) this.remove(key)
  }
}

const state = {
  booting: true,
  user: storage.json('user'),
  profiles: [],
  activeProfile: storage.get('profile') || 'default',
  route: normaliseRoute(location.pathname),
  loadingPage: false,
  mobileMenu: false,
  chatDrawer: false,
  composerDraft: '',
  overview: null,
  sessions: [],
  sessionQuery: '',
  currentSessionId: '',
  messages: [],
  jobs: [],
  audit: [],
  projects: [],
  notifications: [],
  unreadNotifications: 0,
  files: [],
  fileConfig: null,
  prompts: [],
  sessionMetadata: new Map(),
  devices: [],
  users: [],
  diagnostics: null,
  backups: [],
  models: [],
  gatewaySocket: null,
  gatewayConnected: false,
  gatewayProfile: '',
  gatewaySessionId: '',
  gatewayStoredSessionId: '',
  gatewayMessages: [],
  gatewayEvents: [],
  gatewayPending: new Map(),
  gatewayRequests: [],
  gatewayNextId: 1,
  selectedModel: storage.get('model') || '',
  run: null,
  liveText: '',
  toolEvents: [],
  approval: null,
  streamController: null,
  streamError: '',
  lastEventId: '',
  installPrompt: null,
  showSessionCreate: false,
  showJobCreate: false,
  busy: '',
  error: ''
}

const LABELS = {
  home: 'Home',
  chat: 'Chat',
  sessions: 'Conversations',
  automations: 'Scheduled tasks',
  notifications: 'Alerts',
  files: 'Files',
  prompts: 'Saved prompts',
  gateway: 'Live session',
  audit: 'Activity log',
  admin: 'Users',
  settings: 'Settings',
  projects: 'Projects',
  newSession: 'New conversation',
  profile: 'Assistant',
  run: 'Task',
  approval: 'Needs your OK',
}

function applyTheme() {
  const saved = storage.get('hc.theme')
  const theme = saved || (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark')
  document.documentElement.dataset.theme = theme
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'light' ? '#f7f7fb' : '#09090b')
}
applyTheme()

function normaliseRoute(path) {
  const allowed = new Set(['/', '/projects', '/chat', '/sessions', '/automations', '/notifications', '/files', '/prompts', '/gateway', '/audit', '/admin', '/settings'])
  const clean = (path || '/').replace(/\/+$/, '') || '/'
  return allowed.has(clean) ? clean : '/'
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function escapeAttr(value) { return escapeHtml(value).replaceAll('`', '&#096;') }

function safeJson(value) {
  try { return JSON.stringify(value, null, 2) } catch { return String(value ?? '') }
}

function sanitiseBridgeUrl(url) {
  url = (url || '').trim().replace(/\/+$/, '')
  const onPhoneOrRemote = !/^(localhost|127\.0\.0\.1)$/i.test(location.hostname)
  if (onPhoneOrRemote && /^(https?:\/\/)?(localhost|127\.0\.0\.1)(:\d+)?$/i.test(url)) return ''
  return url
}

function bridgeBase() {
  return sanitiseBridgeUrl(storage.get('bridgeUrl') || '')
}

function humanizeNetworkError(error) {
  const raw = error instanceof Error ? error.message : String(error || '')
  if (/failed to fetch|networkerror|load failed|bridge is unreachable/i.test(raw)) {
    return 'Can’t reach the computer running Hermes. Check your VPN/Tailscale is connected and that you opened the exact address you were given. Leave “Server URL” blank.'
  }
  return raw || 'Sign-in failed'
}

function endpoint(path) {
  const clean = path.startsWith('/') ? path : `/${path}`
  return `${bridgeBase()}${clean}`
}

class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : `Request failed (${status})`)
    this.status = status
    this.detail = detail
  }
}

let refreshPromise = null

function saveTokens(tokens) {
  storage.set('access', tokens.access_token)
  storage.set('refresh', tokens.refresh_token)
  storage.set('accessExpires', tokens.access_expires_at)
  storage.set('refreshExpires', tokens.refresh_expires_at)
  storage.setJson('user', tokens.user)
  if (tokens.device_id) storage.set('deviceId', tokens.device_id)
  state.user = tokens.user
}

async function parseError(response) {
  const text = await response.text()
  if (!text) return response.statusText || `HTTP ${response.status}`
  try {
    const body = JSON.parse(text)
    return body.detail ?? body.error ?? body
  } catch { return text }
}

async function refreshAccess() {
  if (refreshPromise) return refreshPromise
  refreshPromise = (async () => {
    const refresh = storage.get('refresh')
    if (!refresh) return false
    try {
      const response = await fetch(endpoint('/api/auth/refresh'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh, device_id: deviceId(), device_name: navigator.userAgent.slice(0, 120) })
      })
      if (!response.ok) {
        storage.clearAuth()
        state.user = null
        return false
      }
      saveTokens(await response.json())
      return true
    } catch { return false }
  })()
  try { return await refreshPromise } finally { refreshPromise = null }
}

async function apiFetch(path, init = {}, options = {}) {
  const auth = options.auth !== false
  const headers = new Headers(init.headers || {})
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (auth) {
    const access = storage.get('access')
    if (access) headers.set('Authorization', `Bearer ${access}`)
  }
  let response
  try { response = await fetch(endpoint(path), { ...init, headers }) }
  catch (error) { throw new ApiError(0, error instanceof Error ? error.message : 'Bridge is unreachable') }

  if (response.status === 401 && auth && options.retry !== false && await refreshAccess()) {
    return apiFetch(path, init, { ...options, retry: false })
  }
  if (!response.ok) throw new ApiError(response.status, await parseError(response))
  if (response.status === 204) return undefined
  const contentType = response.headers.get('content-type') || ''
  return contentType.includes('application/json') ? response.json() : response.text()
}

function toast(message, type = 'info', timeout = 4200) {
  let stack = document.getElementById('toast-stack')
  if (!stack) {
    stack = document.createElement('div')
    stack.id = 'toast-stack'
    stack.className = 'toast-stack'
    stack.setAttribute('role', 'status')
    stack.setAttribute('aria-live', 'polite')
    document.body.appendChild(stack)
  }
  const item = document.createElement('div')
  item.className = `toast-static ${type}`
  const symbol = type === 'success' ? '✓' : type === 'error' ? '!' : 'i'
  item.innerHTML = `<span>${symbol}</span><span></span><button aria-label="Dismiss">×</button>`
  item.children[1].textContent = String(message)
  item.querySelector('button').addEventListener('click', () => item.remove())
  stack.appendChild(item)
  setTimeout(() => item.remove(), type === 'error' ? 8000 : timeout)
}

function sheet({ title, message = '', fields = [], confirmLabel = 'OK', cancelLabel = 'Cancel', danger = false }) {
  return new Promise(resolve => {
    document.querySelectorAll('dialog.sheet').forEach(node => node.remove())
    const dialog = document.createElement('dialog')
    dialog.className = 'sheet'
    const isList = fields.length === 1 && fields[0].type === 'list'
    const inputs = fields.map((field, index) => {
      const id = `sheet-field-${index}`
      if (field.type === 'list') {
        return `<div class="sheet-list" data-list="${escapeAttr(field.name)}">${(field.options || []).map(option => `<button type="button" data-value="${escapeAttr(option.value)}" class="${option.value === field.value ? 'active' : ''} ${option.danger ? 'danger' : ''}"><span>${escapeHtml(option.label)}</span>${option.hint ? `<small>${escapeHtml(option.hint)}</small>` : ''}</button>`).join('')}</div>`
      }
      const control = field.type === 'textarea'
        ? `<textarea id="${id}" name="${escapeAttr(field.name)}" rows="4" placeholder="${escapeAttr(field.placeholder || '')}">${escapeHtml(field.value || '')}</textarea>`
        : field.type === 'select'
          ? `<select id="${id}" name="${escapeAttr(field.name)}">${(field.options || []).map(option => `<option value="${escapeAttr(option.value)}" ${option.value === field.value ? 'selected' : ''}>${escapeHtml(option.label)}</option>`).join('')}</select>`
          : `<input id="${id}" name="${escapeAttr(field.name)}" type="${escapeAttr(field.type || 'text')}" value="${escapeAttr(field.value || '')}" placeholder="${escapeAttr(field.placeholder || '')}" ${field.required ? 'required' : ''}>`
      return `<label for="${id}"><span>${escapeHtml(field.label || '')}</span>${control}${field.hint ? `<small>${escapeHtml(field.hint)}</small>` : ''}</label>`
    }).join('')
    dialog.innerHTML = `<form method="dialog" class="sheet-form">
      <h3>${escapeHtml(title)}</h3>
      ${message ? `<p>${escapeHtml(message)}</p>` : ''}
      ${inputs}
      <footer class="${isList ? 'single' : ''}"><button type="button" value="cancel" class="button button-secondary">${escapeHtml(cancelLabel)}</button>${isList ? '' : `<button type="submit" value="ok" class="button ${danger ? 'button-danger' : 'button-primary'}">${escapeHtml(confirmLabel)}</button>`}</footer>
    </form>`
    const form = dialog.querySelector('form')
    const finish = value => { dialog.close(); dialog.remove(); resolve(value) }
    dialog.querySelector('button[value="cancel"]').addEventListener('click', () => finish(fields.length ? null : false))
    dialog.addEventListener('cancel', event => { event.preventDefault(); finish(fields.length ? null : false) })
    dialog.addEventListener('click', event => { if (event.target === dialog) finish(fields.length ? null : false) })
    form.addEventListener('submit', event => {
      event.preventDefault()
      if (!fields.length) return finish(true)
      const data = new FormData(form)
      const result = Object.fromEntries(fields.map(field => [field.name, String(data.get(field.name) ?? '')]))
      finish(fields.length === 1 ? result[fields[0].name] : result)
    })
    dialog.querySelectorAll('.sheet-list button').forEach(button => button.addEventListener('click', () => finish(button.dataset.value)))
    document.body.appendChild(dialog)
    dialog.showModal()
    const first = dialog.querySelector('input, textarea, select')
    if (first) { first.focus(); if (first.select) first.select() }
  })
}

const ask = (title, value = '', options = {}) => sheet({ title, fields: [{ name: 'value', value, ...options }], confirmLabel: options.confirmLabel || 'Save' })
const okay = (title, message = '', options = {}) => sheet({ title, message, confirmLabel: options.confirmLabel || 'Yes', cancelLabel: options.cancelLabel || 'Cancel', danger: Boolean(options.danger) })

function timestamp(value) {
  if (value === null || value === undefined || value === '') return '—'
  let date
  if (typeof value === 'number') date = new Date(value < 10_000_000_000 ? value * 1000 : value)
  else date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit'
  }).format(date)
}

function relativeTime(value) {
  if (!value) return '—'
  const date = typeof value === 'number' ? new Date(value < 10_000_000_000 ? value * 1000 : value) : new Date(value)
  const seconds = Math.round((date.getTime() - Date.now()) / 1000)
  if (!Number.isFinite(seconds)) return timestamp(value)
  const units = [[60, 'second'], [60, 'minute'], [24, 'hour'], [30, 'day'], [12, 'month']]
  let amount = seconds
  let unit = 'second'
  for (const [size, next] of units) {
    if (Math.abs(amount) < size) break
    amount = Math.round(amount / size)
    unit = next
  }
  return new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(amount, unit)
}

function listFromPayload(payload, keys = []) {
  if (Array.isArray(payload)) return payload
  if (!payload || typeof payload !== 'object') return []
  for (const key of keys) if (Array.isArray(payload[key])) return payload[key]
  for (const value of Object.values(payload)) if (Array.isArray(value)) return value
  return []
}

function sessionId(session) { return String(session?.id || session?.session_id || '') }
function sessionTitle(session) { return String(session?.title || session?.name || session?.label || 'Untitled session') }
function jobId(job) { return String(job?.id || job?.job_id || '') }
function sessionMeta(id) { return state.sessionMetadata.get(String(id)) || { pinned: false, tags: [], note: '' } }
function activeProfile() { return state.profiles.find(item => item.slug === state.activeProfile) }
function permission(name) { return Boolean(activeProfile()?.permissions?.[name]) }

function messageText(message) {
  const value = message?.content ?? message?.text ?? message?.output ?? ''
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(part => {
    if (typeof part === 'string') return part
    if (!part || typeof part !== 'object') return ''
    return part.text ?? part.content ?? part.value ?? ''
  }).filter(Boolean).join('\n')
  if (value && typeof value === 'object') return value.text ?? value.content ?? safeJson(value)
  return String(value || '')
}

function inlineMarkdown(text) {
  let html = escapeHtml(text)
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>')
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
  return html
}

function renderMarkdown(value) {
  const text = String(value || '')
  if (!text.trim()) return '<p class="faint">No text returned.</p>'
  const parts = text.split(/```/)
  return parts.map((part, index) => {
    if (index % 2 === 1) {
      const firstBreak = part.indexOf('\n')
      const body = firstBreak >= 0 ? part.slice(firstBreak + 1) : part
      return `<pre><code>${escapeHtml(body)}</code></pre>`
    }
    const lines = part.split(/\r?\n/)
    const out = []
    let list = null
    const closeList = () => { if (list) { out.push(`</${list}>`); list = null } }
    for (const rawLine of lines) {
      const line = rawLine.trimEnd()
      if (!line.trim()) { closeList(); continue }
      const heading = /^(#{1,3})\s+(.+)$/.exec(line)
      if (heading) { closeList(); const level = heading[1].length; out.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`); continue }
      const bullet = /^[-*]\s+(.+)$/.exec(line)
      if (bullet) { if (list !== 'ul') { closeList(); list = 'ul'; out.push('<ul>') } out.push(`<li>${inlineMarkdown(bullet[1])}</li>`); continue }
      const ordered = /^\d+[.)]\s+(.+)$/.exec(line)
      if (ordered) { if (list !== 'ol') { closeList(); list = 'ol'; out.push('<ol>') } out.push(`<li>${inlineMarkdown(ordered[1])}</li>`); continue }
      if (line.startsWith('> ')) { closeList(); out.push(`<blockquote>${inlineMarkdown(line.slice(2))}</blockquote>`); continue }
      closeList(); out.push(`<p>${inlineMarkdown(line)}</p>`)
    }
    closeList()
    return out.join('')
  }).join('')
}

function icon(symbol) { return `<span class="nav-symbol" aria-hidden="true">${symbol}</span>` }

function profilePicker(compact = false) {
  const profile = activeProfile() || state.profiles[0]
  const options = state.profiles.map(item =>
    `<option value="${escapeAttr(item.slug)}" ${item.slug === state.activeProfile ? 'selected' : ''} ${item.configured ? '' : 'disabled'}>${escapeHtml(item.label)}${item.configured ? '' : ' (not connected)'}</option>`
  ).join('')
  return `<div class="profile-picker ${compact ? 'compact' : ''}" style="--profile-accent:${escapeAttr(profile?.accent || '#8b5cf6')}">
    <span class="profile-picker-icon">${icon('◈')}</span>
    <span class="profile-picker-copy"><small>${escapeHtml(LABELS.profile)}</small><strong>${escapeHtml(profile?.label || 'No assistant')}</strong></span>
    <span class="profile-picker-chevron">⌄</span>
    <select class="profile-picker-native" data-action="profile-change" aria-label="Assistant">${options}</select>
  </div>`
}

function navItem(path, label, symbol) {
  return `<a href="${path}" data-nav="${path}" class="${state.route === path ? 'active' : ''}">${icon(symbol)}<span>${escapeHtml(label)}</span></a>`
}

function tabItem(path, label, symbol, badge = 0) {
  return `<a href="${path}" data-nav="${path}" class="${state.route === path ? 'active' : ''}">${icon(symbol)}${badge ? `<b class="tab-badge">${badge > 99 ? '99+' : badge}</b>` : ''}<span>${escapeHtml(label)}</span></a>`
}

async function openMoreSheet() {
  const pages = [
    ['/projects', LABELS.projects], ['/automations', LABELS.automations], ['/files', LABELS.files],
    ['/prompts', LABELS.prompts], ['/gateway', LABELS.gateway],
    ...(state.user?.role === 'admin' ? [['/audit', LABELS.audit], ['/admin', LABELS.admin]] : []),
    ['/settings', LABELS.settings],
    ['__logout', 'Sign out'],
  ]
  const choice = await sheet({ title: 'More', fields: [{ name: 'page', type: 'list', value: state.route, options: pages.map(([path, label]) => ({ value: path, label, danger: path === '__logout' })) }], cancelLabel: 'Close' })
  if (choice === '__logout') { await logout(); return }
  if (choice) await navigate(choice)
}

function shell(content) {
  const userName = state.user?.email?.split('@')[0] || 'Operator'
  const moreActive = ['/automations','/files','/prompts','/gateway','/audit','/admin','/settings','/projects'].includes(state.route)
  return `<div class="app-shell">
    <div class="offline-banner" hidden>You're offline — showing what was loaded last.</div>
    <header class="mobile-header">
      <div class="brand compact"><span class="brand-mark">H</span><strong>Hermes</strong><span class="brand-version">${escapeHtml(VERSION_LABEL)}</span></div>
      ${profilePicker(true)}
    </header>
    ${state.mobileMenu ? '<button class="mobile-scrim" data-action="mobile-close" aria-label="Close menu"></button>' : ''}
    <aside class="sidebar ${state.mobileMenu ? 'mobile-open' : ''}">
      <div class="sidebar-top">
        <div class="brand"><span class="brand-mark">H</span><span class="brand-copy"><strong>Hermes</strong><small>Companion</small></span></div>
        <button class="icon-button mobile-only" data-action="mobile-close" aria-label="Close menu">×</button>
      </div>
      <div class="desktop-profile">${profilePicker()}</div>
      <nav class="sidebar-nav">
        ${navItem('/', LABELS.home, '◉')}
        ${navItem('/projects', LABELS.projects, '◇')}
        ${navItem('/chat', LABELS.chat, '✦')}
        ${navItem('/sessions', LABELS.sessions, '▤')}
        ${navItem('/automations', LABELS.automations, '◷')}
        ${navItem('/notifications', `${LABELS.notifications}${state.unreadNotifications ? ` (${state.unreadNotifications})` : ''}`, '●')}
        ${navItem('/files', LABELS.files, '⇧')}
        ${navItem('/prompts', LABELS.prompts, '⌘')}
        ${navItem('/gateway', LABELS.gateway, '⌁')}
        ${state.user?.role === 'admin' ? navItem('/audit', LABELS.audit, '✓') + navItem('/admin', LABELS.admin, '♜') : ''}
        ${navItem('/settings', LABELS.settings, '⚙')}
      </nav>
      <div class="sidebar-footer">
        <div class="user-chip"><span>◎</span><div><strong>${escapeHtml(userName)}</strong><small>${escapeHtml(state.user?.role || 'admin')}</small></div></div>
        <button class="sidebar-logout" data-action="logout">${icon('↪')}<span>Sign out</span></button>
      </div>
    </aside>
    <main class="main-content">${content}</main>
    <nav class="tabbar" aria-label="Main">
      ${tabItem('/', LABELS.home, '◉')}
      ${tabItem('/chat', LABELS.chat, '✦')}
      ${tabItem('/sessions', LABELS.sessions, '▤')}
      ${tabItem('/notifications', LABELS.notifications, '●', state.unreadNotifications)}
      <a href="#" data-more class="${moreActive ? 'active' : ''}">${icon('⋯')}<span>More</span></a>
    </nav>
  </div>`
}

function pageHeader(eyebrow, title, description, actions = '') {
  return `<header class="page-header"><div><span class="eyebrow">${escapeHtml(eyebrow)}</span><h1>${escapeHtml(title)}</h1><p>${escapeHtml(description)}</p></div>${actions ? `<div class="page-actions">${actions}</div>` : ''}</header>`
}

function loadingPanel(label = 'Loading') {
  return `<div class="panel-loader"><div><div class="loading-spinner"></div><p class="muted" style="margin-top:12px">${escapeHtml(label)}</p></div></div>`
}

function emptyState(title, description, action = '') {
  return `<div class="empty-state"><div><strong>${escapeHtml(title)}</strong><p>${escapeHtml(description)}</p>${action}</div></div>`
}

function renderLogin() {
  const bridge = storage.get('bridgeUrl') || ''
  ROOT.innerHTML = `<div class="login-page">
    <section class="login-intro">
      <div class="login-brand brand"><span class="brand-mark">H</span><span class="brand-copy"><strong>Hermes</strong><small>Companion</small></span></div>
      <div class="login-copy"><span class="eyebrow">YOUR ASSISTANTS</span><h1>Hermes on your phone.</h1><p>Chat, approvals and scheduled tasks — same assistants as the desktop app.</p></div>
      <div class="login-features">
        <div><span>◈</span><span><strong>Same assistants</strong><small class="faint">Hermes Core, Mentos and specialists</small></span></div>
        <div><span>↻</span><span><strong>Pick up later</strong><small class="faint">Conversations survive when the phone sleeps</small></span></div>
        <div><span>⌾</span><span><strong>Keys stay here</strong><small class="faint">Nothing secret lives in the browser</small></span></div>
      </div>
    </section>
    <section class="static-login-panel">
      <div class="static-login-card">
        <div class="brand"><span class="brand-mark">H</span><span class="brand-copy"><strong>Hermes Companion</strong><small>Secure bridge login</small></span></div>
        <h2>Sign in</h2><p>Use the email and password set up for this app.</p>
        ${state.error ? `<div class="app-notice error"><span>!</span><span>${escapeHtml(state.error)}</span></div>` : ''}
        <form id="login-form">
          <label><span>Email</span><input name="email" type="email" required autocomplete="username" placeholder="you@example.com"></label>
          <label><span>Password</span><input name="password" type="password" required autocomplete="current-password" minlength="12"></label>
          <button class="button button-primary" type="submit" ${state.busy === 'login' ? 'disabled' : ''}>${state.busy === 'login' ? 'Signing in…' : 'Sign in'}</button>
          <button class="button button-secondary" type="button" data-action="passkey-login" ${state.busy === 'login' ? 'disabled' : ''}>Sign in with passkey</button>
          <details class="login-advanced"><summary>Advanced</summary><label><span>Server URL</span><input name="bridge" value="${escapeAttr(sanitiseBridgeUrl(bridge))}" placeholder="Leave blank" autocomplete="url"><small>Leave blank. Only fill this if you were told to.</small></label></details>
        </form>
        <div class="static-login-foot">Your assistants stay on your own computer. This app only talks to it.<span class="brand-version">${escapeHtml(VERSION_LABEL)}</span></div>
      </div>
    </section>
  </div>`
}

function renderBoot() {
  ROOT.innerHTML = `<div class="loading-screen"><div class="brand"><span class="brand-mark">H</span><span class="brand-copy"><strong>Hermes Companion</strong><small>Starting</small></span></div><div class="loading-spinner"></div></div>`
}

function renderChecklist() {
  if (storage.get('hc.checklistDismissed') === '1') return ''
  const installed = window.matchMedia('(display-mode: standalone)').matches
  const pushOn = Boolean(state.push && state.push.subscribed)
  const passkeyOn = Boolean(state.passkeys && (state.passkeys.credentials || []).length)
  const items = [
    { done: installed, label: 'Add to home screen', hint: 'Opens like a normal app.', action: state.installPrompt ? 'install-pwa' : '', fallback: 'In your browser menu choose “Add to Home Screen”.' },
    { done: pushOn, label: 'Turn on alerts', hint: 'Know when a task finishes or needs your OK.', action: 'push-toggle' },
    { done: passkeyOn, label: 'Add a passkey', hint: 'Sign in with your fingerprint or face.', action: 'passkey-add' },
  ]
  if (items.every(item => item.done)) { storage.set('hc.checklistDismissed', '1'); return '' }
  return `<section class="checklist"><header><strong>Get set up</strong><button class="icon-button" data-action="checklist-dismiss" aria-label="Dismiss">×</button></header>
    ${items.map(item => `<div class="checklist-item ${item.done ? 'done' : ''}"><span>${item.done ? '✓' : '○'}</span><div><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.done ? 'Done' : item.hint)}</small>${!item.done && !item.action && item.fallback ? `<small>${escapeHtml(item.fallback)}</small>` : ''}</div>${!item.done && item.action ? `<button class="button button-sm button-primary" data-action="${item.action}">Do it</button>` : ''}</div>`).join('')}
  </section>`
}

function renderOverview() {
  const overview = state.overview || {}
  const attention = overview.attention || { unread: state.unreadNotifications, approvals: 0 }
  const statuses = new Map((overview.statuses || []).map(item => [item.profile, item]))
  const recent = filteredSessions().slice(0, 5)
  const needs = []
  if (attention.approvals) needs.push(`<button class="attention-card urgent" data-nav="/notifications"><strong>${attention.approvals} ${attention.approvals === 1 ? 'task needs' : 'tasks need'} your OK</strong><span>Tap to review</span></button>`)
  if (attention.unread) needs.push(`<button class="attention-card" data-nav="/notifications"><strong>${attention.unread} new ${attention.unread === 1 ? 'alert' : 'alerts'}</strong><span>Finished tasks and updates</span></button>`)
  if (state.run && state.run.status === 'running') needs.push(`<button class="attention-card" data-nav="/chat"><strong>A task is running</strong><span>${escapeHtml(activeProfile()?.label || 'Assistant')} is working — tap to watch</span></button>`)
  const assistants = state.profiles.map(profile => {
    const status = statuses.get(profile.slug)
    const online = profile.configured && status?.online
    const note = !profile.configured ? 'Not connected on this computer' : online ? 'Ready' : 'Offline'
    return `<button class="assistant-card" data-action="open-profile-chat" data-profile="${escapeAttr(profile.slug)}" ${!profile.configured ? 'disabled' : ''}>
      <span class="agent-color" style="background:${escapeAttr(profile.accent || '#8b5cf6')}"></span>
      <span class="assistant-copy"><strong>${escapeHtml(profile.label)}</strong><small>${escapeHtml(profile.description || '')}</small></span>
      <span class="status-pill ${online ? 'online' : 'offline'}">${note}</span>
    </button>`
  }).join('')
  const recentRows = recent.map(session => `<button class="recent-row" data-action="open-session" data-session="${escapeAttr(sessionId(session))}"><strong>${escapeHtml(sessionTitle(session))}</strong><small>${escapeHtml(relativeTime(session.last_active || session.updated_at || session.created_at))}</small></button>`).join('')
  return `<div class="page">
    ${pageHeader('OVERVIEW', LABELS.home, 'Your assistants, recent conversations and anything waiting for you.', '<button class="button button-secondary" data-action="refresh" aria-label="Refresh">↻ Refresh</button>')}
    ${renderChecklist()}
    <section class="section-block"><div class="section-heading"><div><h2>Needs your attention</h2></div></div>${needs.length ? `<div class="attention-grid">${needs.join('')}</div>` : '<p class="faint all-clear">✓ Nothing waiting for you.</p>'}</section>
    <section class="section-block"><div class="section-heading"><div><h2>Assistants</h2></div></div><div class="assistant-grid">${assistants}</div></section>
    <section class="section-block"><div class="section-heading"><div><h2>Recent conversations</h2></div><button class="button button-sm button-secondary" data-nav="/sessions">See all</button></div>${recentRows ? `<div class="recent-list">${recentRows}</div>` : emptyState('No conversations yet', 'Pick an assistant above to start one.')}</section>
  </div>`
}

function filteredSessions() {
  const q = state.sessionQuery.trim().toLowerCase()
  const filtered = q ? state.sessions.filter(item => {
    const meta = sessionMeta(sessionId(item))
    return [sessionTitle(item), item.preview, sessionId(item), meta.note, ...(meta.tags || [])]
      .some(value => String(value || '').toLowerCase().includes(q))
  }) : [...state.sessions]
  return filtered.sort((a, b) => {
    const pinned = Number(sessionMeta(sessionId(b)).pinned) - Number(sessionMeta(sessionId(a)).pinned)
    if (pinned) return pinned
    return Number(b.last_active || b.updated_at || b.created_at || 0) - Number(a.last_active || a.updated_at || a.created_at || 0)
  })
}

function renderSessions() {
  const profile = activeProfile()
  const actions = permission('session_write') ? `<button class="button button-primary" data-action="toggle-session-create">＋ ${LABELS.newSession}</button>` : ''
  const create = state.showSessionCreate ? `<form class="inline-form" id="session-create-form"><label><span>Title</span><input name="title" placeholder="Research, build or coordination task" autofocus></label><button class="button button-primary" type="submit" ${state.busy === 'session-create' ? 'disabled' : ''}>Create and open</button></form>` : ''
  const rows = filteredSessions().map(session => {
    const id = sessionId(session)
    const meta = sessionMeta(id)
    const tags = (meta.tags || []).map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('')
    return `<article class="session-card ${meta.pinned ? 'pinned' : ''}">
      <button class="session-card-main" data-action="open-session" data-session="${escapeAttr(id)}">
        <strong>${meta.pinned ? '★ ' : ''}${escapeHtml(sessionTitle(session))}</strong>
        <small>${escapeHtml(meta.note || session.preview || 'Open conversation')}</small>
        <span class="session-card-meta">${escapeHtml(relativeTime(session.last_active || session.updated_at || session.created_at))}${tags ? ` · ${tags}` : ''}</span>
      </button>
      <button class="icon-button" data-action="session-menu" data-session="${escapeAttr(id)}" aria-label="More options">⋯</button>
    </article>`
  }).join('')
  return `<div class="page">
    ${pageHeader((profile?.label || 'ASSISTANT').toUpperCase(), LABELS.sessions, 'Every conversation with this assistant, shared with the desktop app.', actions)}
    ${create}
    <div class="toolbar-row"><label class="search-box"><input id="session-search" value="${escapeAttr(state.sessionQuery)}" placeholder="Search title or note"></label><button class="button button-secondary" data-action="refresh" aria-label="Refresh">↻ Refresh</button></div>
    ${state.loadingPage ? loadingPanel('Loading conversations') : rows ? `<div class="session-list">${rows}</div>` : emptyState('No matching conversations', state.sessionQuery ? 'Change the search query.' : 'Start the first conversation with this assistant.', permission('session_write') ? `<button class="button button-primary" data-action="toggle-session-create">${LABELS.newSession}</button>` : '')}
  </div>`
}

function renderMessage(message, index) {
  if (message?.display_kind === 'hidden') return ''
  const role = String(message?.role || 'assistant').toLowerCase()
  const isUser = role === 'user'
  const label = isUser ? 'You' : role === 'assistant' ? activeProfile()?.label || 'Hermes' : role
  const text = messageText(message)
  return `<article class="message ${isUser ? 'message-user' : 'message-assistant'}">
    <span class="message-avatar">${isUser ? 'YOU' : 'H'}</span>
    <div class="message-body"><header><strong>${escapeHtml(label)}</strong><span>${escapeHtml(timestamp(message?.created_at || message?.timestamp || ''))}</span></header><div class="message-content">${renderMarkdown(text)}</div></div>
  </article>`
}

function renderToolTimeline() {
  if (!state.toolEvents.length) return ''
  return `<div class="tool-timeline">${state.toolEvents.slice(-30).map(event => `<div class="tool-event ${event.error ? 'error' : ''}"><span>${event.event?.includes('complete') ? '✓' : '↻'}</span><div><strong>${escapeHtml(event.tool || event.event || 'tool')}</strong><small>${escapeHtml(event.preview || event.summary || event.status || '')}</small></div><code>${event.duration ? `${escapeHtml(event.duration)}s` : ''}</code></div>`).join('')}</div>`
}

function renderApproval() {
  if (!state.approval || !state.run) return ''
  const approval = state.approval
  const what = approval.description || approval.reason || approval.command || 'The assistant wants to do something that needs your OK.'
  const command = approval.command && approval.command !== what ? `<code class="approval-command">${escapeHtml(approval.command)}</code>` : ''
  return `<section class="approval-card-static" role="alertdialog" aria-labelledby="approval-title">
    <h3 id="approval-title">${escapeHtml(LABELS.approval)}</h3>
    <p>${escapeHtml(what)}</p>
    ${command}
    <details><summary>Technical details</summary><pre>${escapeHtml(safeJson(approval))}</pre></details>
    <footer><button class="button button-danger" data-action="run-deny">Don’t allow</button><button class="button button-primary" data-action="run-approve">Allow once</button></footer>
  </section>`
}

function renderChatMessages() {
  const transcript = state.messages.map(renderMessage).join('')
  const live = state.run || state.liveText ? `<article class="message message-assistant live-message"><span class="message-avatar">H</span><div class="message-body"><header><strong>${escapeHtml(activeProfile()?.label || 'Hermes')}</strong><span class="streaming-label">${escapeHtml(state.run?.status || 'streaming')}</span></header><div class="message-content">${state.liveText ? renderMarkdown(state.liveText) : '<div class="thinking-row"><span></span><span></span><span></span></div>'}</div></div></article>` : ''
  return `${transcript}${renderToolTimeline()}${renderApproval()}${live}${state.streamError ? `<div class="app-notice error"><span>!</span><span>${escapeHtml(state.streamError)} <button class="button button-sm button-secondary" data-action="run-reconnect">Reconnect</button></span></div>` : ''}`
}

function runControls() {
  if (!state.run) return '<span class="faint">No task running</span><div></div>'
  const status = state.run.status || 'running'
  return `<span><span class="status-pill ${escapeAttr(status)}">${escapeHtml(status)}</span><code>${escapeHtml(state.run.run_id || '')}</code></span><div>${permission('run_control') && status === 'running' ? '<button class="button button-sm button-secondary" data-action="run-steer">Steer</button><button class="button button-sm button-danger" data-action="run-stop">Stop</button>' : ''}</div>`
}

function renderChat() {
  const session = state.sessions.find(item => sessionId(item) === state.currentSessionId)
  const sessionRows = state.sessions.map(item => {
    const id = sessionId(item)
    return `<button class="chat-session-row ${id === state.currentSessionId ? 'active' : ''}" data-action="open-session" data-session="${escapeAttr(id)}"><strong>${escapeHtml(sessionTitle(item))}</strong><small>${escapeHtml(item.preview || relativeTime(item.last_active || item.updated_at))}</small></button>`
  }).join('')
  const modelOptions = ['<option value="">Default</option>', ...state.models.map(model => `<option value="${escapeAttr(model.id)}" ${model.id === state.selectedModel ? 'selected' : ''}>${escapeHtml(model.label)}</option>`)].join('')
  const canChat = permission('chat') && Boolean(state.currentSessionId)
  return `<div class="chat-page">
    ${state.chatDrawer ? '<button class="chat-drawer-scrim-static" data-action="chat-drawer-close" aria-label="Close sessions"></button>' : ''}
    <aside class="chat-sessions ${state.chatDrawer ? 'open' : ''}"><div class="chat-sessions-header"><strong>${escapeHtml(activeProfile()?.label || 'Hermes')}</strong><button class="button button-sm button-primary" data-action="quick-new-session" ${!permission('session_write') ? 'disabled' : ''}>＋ ${LABELS.newSession}</button></div><div class="chat-session-list">${sessionRows || '<div class="faint" style="padding:16px">No conversations</div>'}</div></aside>
    <section class="chat-workspace">
      <header class="chat-header"><div class="chat-header-left"><button class="button button-sm button-secondary chat-drawer-toggle" data-action="chat-drawer-open">${LABELS.sessions}</button><div class="chat-title"><strong>${escapeHtml(session ? sessionTitle(session) : 'Select a conversation')}</strong><small>${session ? escapeHtml(relativeTime(session.last_active || session.updated_at)) : 'No conversation selected'}</small></div></div><div class="chat-header-actions"><label class="model-label"><span>Model</span><select class="model-select" data-action="model-change">${modelOptions}</select></label><button class="icon-button" data-action="refresh" aria-label="Refresh" title="Refresh">↻</button></div></header>
      <div class="chat-scroll" id="chat-scroll">${state.loadingPage ? loadingPanel('Loading transcript') : state.currentSessionId ? `<div class="message-column" id="message-column">${renderChatMessages()}</div>` : '<div class="chat-empty"><div><strong>No conversation selected</strong><p>Pick a conversation on the left, or start a new one.</p></div></div>'}</div>
      <button class="scroll-bottom" data-action="scroll-bottom" aria-label="Jump to latest">↓</button>
      <div class="composer-zone"><div class="run-toolbar" id="run-toolbar">${runControls()}</div><form class="composer" id="composer-form"><textarea name="message" rows="1" placeholder="Message ${escapeAttr(activeProfile()?.label || 'Hermes')}…" ${!canChat || state.run?.status === 'waiting_for_approval' ? 'disabled' : ''}>${escapeHtml(state.composerDraft)}</textarea><button class="send-button" type="submit" aria-label="Send" ${!canChat || state.busy === 'send' ? 'disabled' : ''}>➤</button></form><small>The assistant may use tools. When it needs your OK you’ll see a card here.</small></div>
    </section>
  </div>`
}

function isPaused(job) { return job?.paused === true || job?.enabled === false || job?.status === 'paused' }

function renderAutomations() {
  const profile = activeProfile()
  const active = state.jobs.filter(job => !isPaused(job)).length
  const actions = `<button class="button button-secondary" data-action="refresh">↻ Refresh</button>${permission('jobs_write') ? '<button class="button button-primary" data-action="toggle-job-create">＋ New job</button>' : ''}`
  const create = state.showJobCreate ? `<form class="inline-form cols-3" id="job-create-form"><label><span>Name</span><input name="name" required placeholder="Daily Hermes study"></label><label><span>Schedule</span><input name="schedule" required placeholder="0 9 * * *"></label><label><span>Prompt</span><textarea name="prompt" required rows="3" placeholder="Study current official Hermes releases and report material changes."></textarea></label><button class="button button-primary" type="submit" ${state.busy === 'job-create' ? 'disabled' : ''}>Create</button></form>` : ''
  const jobs = state.jobs.map(job => {
    const id = jobId(job)
    const paused = isPaused(job)
    return `<article class="job-card"><header><span class="status-pill ${paused ? '' : 'online'}">${paused ? 'paused' : 'active'}</span><code>${escapeHtml(id.slice(0, 14))}</code></header><h3>${escapeHtml(job.name || 'Unnamed automation')}</h3><p>${escapeHtml(job.prompt || job.description || 'No prompt preview available.')}</p><div class="job-details"><span>Schedule: ${escapeHtml(job.schedule || 'Not reported')}</span><span>Next: ${escapeHtml(timestamp(job.next_run_at))}</span></div><footer>${permission('jobs_write') ? `<button class="button button-sm button-secondary" data-action="job-run" data-job="${escapeAttr(id)}">Run now</button><button class="button button-sm button-secondary" data-action="job-toggle" data-job="${escapeAttr(id)}" data-paused="${paused ? '1' : '0'}">${paused ? 'Resume' : 'Pause'}</button><button class="button button-sm button-danger" data-action="job-delete" data-job="${escapeAttr(id)}">Delete</button>` : '<span class="faint">Read only</span>'}</footer></article>`
  }).join('')
  return `<div class="page">
    ${pageHeader((profile?.label || 'ASSISTANT').toUpperCase(), LABELS.automations, 'Tasks this assistant runs on a schedule.', actions)}
    <section class="automation-summary"><div><span class="metric-icon">◷</span><div><small>Total jobs</small><strong>${state.jobs.length}</strong></div></div><div><span class="metric-icon">▶</span><div><small>Active</small><strong>${active}</strong></div></div><div><span class="metric-icon">Ⅱ</span><div><small>Paused</small><strong>${state.jobs.length - active}</strong></div></div></section>
    ${!permission('jobs_write') ? '<div class="app-notice warn"><span>!</span><span>This profile’s remote job mutations are disabled by bridge policy. Existing jobs remain visible.</span></div>' : ''}
    ${create}
    ${state.loadingPage ? loadingPanel('Loading automations') : jobs ? `<div class="job-grid">${jobs}</div>` : emptyState('No automations', permission('jobs_write') ? 'Create a gateway-backed routine for this profile.' : 'No jobs were returned for this profile.')}
  </div>`
}

function renderAudit() {
  const rows = state.audit.map(event => `<article class="audit-row"><span class="audit-icon">✓</span><div class="audit-main"><strong>${escapeHtml(event.event)}</strong><p>${escapeHtml(Object.entries(event.metadata || {}).map(([key,value]) => `${key}=${typeof value === 'object' ? safeJson(value) : String(value)}`).join(' · ') || 'No additional metadata')}</p></div><div class="audit-meta"><code>${escapeHtml(event.profile || 'bridge')}</code><span>${escapeHtml(event.email || 'system')} · ${escapeHtml(timestamp(event.created_at))}</span></div></article>`).join('')
  return `<div class="page">${pageHeader('ACTIVITY', LABELS.audit, 'Security-sensitive actions taken in this app.', '<button class="button button-secondary" data-action="refresh" aria-label="Refresh">↻ Refresh</button>')}<div class="app-notice"><span>✓</span><span>Passwords and API keys are never written here.</span></div>${state.loadingPage ? loadingPanel('Loading activity') : rows ? `<div class="audit-list">${rows}</div>` : emptyState('No activity yet', 'Security-sensitive actions will appear here.')}</div>`
}


function renderProjects() {
  const cards = state.projects.map(project => {
    const profile = project.profile || {}
    const sessions = (project.sessions || []).map(item => `<button class="mini-row" data-action="project-session" data-profile="${escapeAttr(profile.slug)}" data-session="${escapeAttr(sessionId(item))}"><strong>${escapeHtml(sessionTitle(item))}</strong><small>${escapeHtml(item.preview || sessionId(item))}</small></button>`).join('')
    const jobs = (project.jobs || []).map(item => `<div class="mini-row static"><strong>${escapeHtml(item.name || item.title || jobId(item) || 'Automation')}</strong><small>${escapeHtml(item.schedule || item.status || (item.enabled === false ? 'paused' : 'active'))}</small></div>`).join('')
    return `<article class="project-card" style="--profile-accent:${escapeAttr(profile.accent || '#8b5cf6')}">
      <header><div><span class="project-dot"></span><h2>${escapeHtml(profile.label || profile.slug)}</h2></div><span class="status-pill ${project.online ? 'online' : 'offline'}">${project.online ? 'online' : 'offline'}</span></header>
      <p>${escapeHtml(profile.description || 'Hermes project profile')}</p>
      <div class="project-metrics"><span><small>Sessions returned</small><strong>${project.session_count_returned || 0}</strong></span><span><small>Automations</small><strong>${project.job_count || 0}</strong></span><span><small>Active jobs</small><strong>${project.active_job_count || 0}</strong></span></div>
      <div class="project-columns"><section><h3>Recent sessions</h3>${sessions || '<p class="faint">No sessions returned.</p>'}</section><section><h3>Automations</h3>${jobs || '<p class="faint">No automations returned.</p>'}</section></div>
      <footer><span class="faint">${escapeHtml(profile.project_kind || 'general')}</span><button class="button button-sm button-primary" data-action="open-profile-chat" data-profile="${escapeAttr(profile.slug)}">Open profile</button></footer>
    </article>`
  }).join('')
  return `<div class="page">
    ${pageHeader('PROJECTS', LABELS.projects, 'A live overview of the assistants available in this app.', '<button class="button button-secondary" data-action="refresh" aria-label="Refresh">↻ Refresh</button>')}
    ${state.loadingPage ? loadingPanel('Loading project fleet') : cards ? `<div class="project-grid">${cards}</div>` : emptyState('No projects available', 'No configured Hermes profile is assigned to this account.')}
  </div>`
}

function renderNotifications() {
  const actions = `<button class="button button-secondary" data-action="notifications-read-all" ${state.unreadNotifications ? '' : 'disabled'}>Mark all read</button><button class="button button-secondary" data-action="notifications-permission">Browser alerts</button>`
  const rows = state.notifications.map(item => `<article class="notification-card ${item.read_at ? 'read' : 'unread'} ${escapeAttr(item.severity || 'info')}">
    <span class="notification-symbol">${item.severity === 'error' ? '!' : item.severity === 'warning' ? '△' : item.severity === 'success' ? '✓' : 'i'}</span>
    <div><header><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(relativeTime(item.created_at))}</span></header><p>${escapeHtml(item.message || '')}</p><footer><span>${escapeHtml(item.kind)}</span>${item.kind === 'approval' ? `<button class="button button-sm button-primary" data-action="notification-open" data-id="${escapeAttr(item.id)}">Review</button>` : ((item.metadata && item.metadata.session_id) ? `<button class="button button-sm button-secondary" data-action="notification-open" data-id="${escapeAttr(item.id)}">Open</button>` : '')}</footer></div>
    <div class="notification-actions">${item.read_at ? `<button title="Mark unread" aria-label="Mark unread" data-action="notification-read" data-read="0" data-id="${escapeAttr(item.id)}">○</button>` : `<button title="Mark read" aria-label="Mark read" data-action="notification-read" data-read="1" data-id="${escapeAttr(item.id)}">✓</button>`}<button class="danger" title="Delete" aria-label="Delete" data-action="notification-delete" data-id="${escapeAttr(item.id)}">×</button></div>
  </article>`).join('')
  return `<div class="page">
    ${pageHeader('INBOX', LABELS.notifications, 'Finished tasks, problems, and anything that needs your OK.', actions)}
    <section class="metric-grid compact-metrics"><article class="metric-card"><span class="metric-icon">●</span><span class="metric-copy"><small>Unread</small><strong>${state.unreadNotifications}</strong></span></article><article class="metric-card"><span class="metric-icon">▤</span><span class="metric-copy"><small>Loaded</small><strong>${state.notifications.length}</strong></span></article></section>
    ${state.loadingPage ? loadingPanel('Loading notifications') : rows ? `<div class="notification-list">${rows}</div>` : emptyState('Inbox is clear', 'Run events and approval requests will appear here.')}
  </div>`
}

function renderFiles() {
  const config = state.fileConfig || {}
  const upload = permission('files_write') ? `<form id="file-upload-form" class="upload-drop"><div><span class="upload-icon">⇧</span><strong>Upload to ${escapeHtml(activeProfile()?.label || state.activeProfile)}</strong><p>Files are isolated by user and profile, hashed, optionally scanned, and never written to an arbitrary path.</p></div><label class="button button-primary"><input name="file" type="file" hidden required>Choose file</label><input type="hidden" name="profile" value="${escapeAttr(state.activeProfile)}"></form>` : ''
  const rows = state.files.map(item => `<tr><td><strong>${escapeHtml(item.original_name)}</strong><small>${escapeHtml(item.mime_type || '')}</small></td><td>${escapeHtml(formatBytes(item.size_bytes))}</td><td><code>${escapeHtml(String(item.sha256 || '').slice(0, 12))}…</code></td><td><span class="status-pill ${item.scan_status === 'clean' ? 'online' : 'neutral'}">${escapeHtml(item.scan_status)}</span></td><td><div class="table-actions"><button data-action="file-copy" data-path="${escapeAttr(item.hermes_path)}" title="Copy Hermes path">⧉</button><a href="${escapeAttr(endpoint(`/api/files/${encodeURIComponent(item.id)}/download`))}" data-file-download="${escapeAttr(item.id)}" title="Download">⇩</a>${permission('files_write') ? `<button class="danger" data-action="file-delete" data-id="${escapeAttr(item.id)}" title="Delete">×</button>` : ''}</div></td></tr>`).join('')
  return `<div class="page">
    ${pageHeader('FILES', LABELS.files, 'Send files to an assistant. They are scanned before use.', '<button class="button button-secondary" data-action="refresh" aria-label="Refresh">↻ Refresh</button>')}
    ${upload}
    <div class="file-policy"><span>Maximum: <strong>${escapeHtml(formatBytes(config.max_upload_bytes || 0))}</strong></span><span>Scanner: <strong>${config.scanner_configured ? 'configured' : 'structural validation only'}</strong></span><span>Allowed types: <strong>${(config.allowed_extensions || []).length}</strong></span></div>
    ${state.loadingPage ? loadingPanel('Loading files') : rows ? `<div class="session-table-wrap"><table class="session-table file-table"><thead><tr><th>File</th><th>Size</th><th>SHA-256</th><th>Scan</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>` : emptyState('No files staged', 'Upload a file to create a controlled path Hermes can access.')}
  </div>`
}

function renderPrompts() {
  const cards = state.prompts.map(item => `<article class="prompt-card"><header><div><strong>${escapeHtml(item.title)}</strong><code>${escapeHtml(item.profile || 'all profiles')}</code></div><span>${escapeHtml(relativeTime(item.updated_at))}</span></header><pre>${escapeHtml(item.prompt)}</pre><footer><button class="button button-sm button-primary" data-action="prompt-use" data-id="${escapeAttr(item.id)}">Use in chat</button><button class="button button-sm button-secondary" data-action="prompt-edit" data-id="${escapeAttr(item.id)}">Edit</button><button class="button button-sm button-danger" data-action="prompt-delete" data-id="${escapeAttr(item.id)}">Delete</button></footer></article>`).join('')
  const options = ['<option value="">All profiles</option>', ...state.profiles.filter(item => item.configured).map(item => `<option value="${escapeAttr(item.slug)}">${escapeHtml(item.label)}</option>`)].join('')
  return `<div class="page">
    ${pageHeader('PROMPTS', LABELS.prompts, 'Reusable instructions you can drop into a conversation.')}
    <form id="prompt-create-form" class="inline-form prompt-form"><label><span>Title</span><input name="title" maxlength="160" required placeholder="Deep code review"></label><label><span>Profile scope</span><select name="profile">${options}</select></label><label class="span-all"><span>Prompt</span><textarea name="prompt" rows="5" maxlength="100000" required placeholder="Describe the reusable task…"></textarea></label><button class="button button-primary" type="submit">Save prompt</button></form>
    ${state.loadingPage ? loadingPanel('Loading prompts') : cards ? `<div class="prompt-grid">${cards}</div>` : emptyState('No saved prompts', 'Save a reusable instruction above.')}
  </div>`
}

function renderGatewayRequest(request) {
  const params = request.params || {}
  if (request.method === 'approval') return `<article class="gateway-request"><h3>Approval requested</h3><p>${escapeHtml(params.description || params.command || 'Hermes requests approval.')}</p><pre>${escapeHtml(safeJson(params))}</pre><footer><button class="button button-danger" data-action="gateway-answer" data-request="${escapeAttr(request.id)}" data-choice="deny">Deny</button><button class="button button-primary" data-action="gateway-answer" data-request="${escapeAttr(request.id)}" data-choice="once">Approve once</button></footer></article>`
  if (request.method === 'clarify') return `<article class="gateway-request"><h3>Hermes asks</h3><p>${escapeHtml(params.question || params.prompt || params.message || safeJson(params))}</p><form data-gateway-clarify="${escapeAttr(request.id)}"><input name="answer" required placeholder="Your answer"><button class="button button-primary" type="submit">Answer</button></form></article>`
  return `<article class="gateway-request"><h3>${escapeHtml(request.method)}</h3><p>This Companion does not expose a safe UI for this request type.</p><button class="button button-danger" data-action="gateway-reject" data-request="${escapeAttr(request.id)}">Reject unsupported request</button></article>`
}

function renderGateway() {
  const available = Boolean(activeProfile()?.gateway_available)
  const transcript = state.gatewayMessages.map((message, index) => renderMessage(message, index)).join('')
  const events = state.gatewayEvents.slice(-40).map(item => `<div class="gateway-event"><code>${escapeHtml(item.type || item.method || 'event')}</code><span>${escapeHtml(item.summary || item.payload?.tool || item.payload?.status || '')}</span></div>`).join('')
  const requests = state.gatewayRequests.map(renderGatewayRequest).join('')
  return `<div class="page gateway-page">
    ${pageHeader('LIVE', LABELS.gateway, 'Talk to an assistant in real time, exactly like the desktop app.', `<button class="button ${state.gatewayConnected ? 'button-danger' : 'button-primary'}" data-action="gateway-toggle" ${available ? '' : 'disabled'}>${state.gatewayConnected ? 'Disconnect' : 'Connect'}</button>`)}
    ${!available ? '<div class="app-notice"><span>i</span><span>Live session is not turned on. Regular chat still works.</span></div>' : ''}
    <section class="gateway-status"><span class="status-pill ${state.gatewayConnected ? 'online' : 'offline'}">${state.gatewayConnected ? 'connected' : 'disconnected'}</span><code>${escapeHtml(state.gatewaySessionId || 'no live session')}</code><span class="faint">${escapeHtml(activeProfile()?.label || state.activeProfile)}</span></section>
    <div class="gateway-layout"><section class="gateway-main"><div class="gateway-toolbar"><button class="button button-sm button-secondary" data-action="gateway-list" ${state.gatewayConnected ? '' : 'disabled'}>List sessions</button><button class="button button-sm button-secondary" data-action="gateway-new" ${state.gatewayConnected ? '' : 'disabled'}>New live session</button><button class="button button-sm button-secondary" data-action="gateway-resume" ${state.gatewayConnected ? '' : 'disabled'}>Resume stored session</button><button class="button button-sm button-danger" data-action="gateway-interrupt" ${state.gatewayConnected && state.gatewaySessionId ? '' : 'disabled'}>Interrupt</button></div><div class="gateway-transcript">${transcript || emptyState('No live transcript', 'Connect and create or resume a live session.')}</div>${requests}<form id="gateway-composer" class="gateway-composer"><textarea name="text" rows="3" placeholder="Send through prompt.submit…" ${state.gatewayConnected && state.gatewaySessionId ? '' : 'disabled'}></textarea><button class="button button-primary" type="submit" ${state.gatewayConnected && state.gatewaySessionId ? '' : 'disabled'}>Send</button></form></section><aside class="gateway-events"><h2>Live events</h2>${events || '<p class="faint">No events yet.</p>'}</aside></div>
  </div>`
}

function renderAdmin() {
  if (state.user?.role !== 'admin') return `<div class="page">${emptyState('Administrator access required', 'This page is restricted.')}</div>`
  const profileOptions = state.profiles.map(item => `<label class="check-chip"><input type="checkbox" name="profiles" value="${escapeAttr(item.slug)}"><span>${escapeHtml(item.label)}</span></label>`).join('')
  const users = state.users.map(user => `<article class="user-card"><header><div><strong>${escapeHtml(user.email)}</strong><code>${escapeHtml(user.role)}</code></div><span class="status-pill ${user.active ? 'online' : 'offline'}">${user.active ? 'active' : 'disabled'}</span></header><div class="tag-row">${(user.profiles || []).map(profile => `<span class="tag">${escapeHtml(profile)}</span>`).join('') || (user.role === 'admin' ? '<span class="tag">All configured profiles</span>' : '<span class="faint">No profiles assigned</span>')}</div><footer><button class="button button-sm button-secondary" data-action="admin-edit" data-id="${escapeAttr(user.id)}">Edit access</button><button class="button button-sm button-secondary" data-action="admin-reset-password" data-id="${escapeAttr(user.id)}">Reset password</button>${user.id !== state.user.id ? `<button class="button button-sm button-danger" data-action="admin-delete" data-id="${escapeAttr(user.id)}">Delete</button>` : ''}</footer></article>`).join('')
  const backups = state.backups.map(item => `<div class="backup-row"><div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(formatBytes(item.bytes))} · ${escapeHtml(timestamp(item.created_at))}</small></div><div><a class="button button-sm button-secondary" href="${escapeAttr(endpoint(`/api/backups/${encodeURIComponent(item.name)}`))}" data-backup-download="${escapeAttr(item.name)}">Download</a><button class="button button-sm button-danger" data-action="backup-delete" data-name="${escapeAttr(item.name)}">Delete</button></div></div>`).join('')
  return `<div class="page">
    ${pageHeader('USERS', LABELS.admin, 'Accounts, access and backups for this app.')}
    <form id="admin-user-form" class="admin-create"><div class="inline-form cols-3"><label><span>Email</span><input name="email" type="email" required></label><label><span>Initial password</span><input name="password" type="password" minlength="12" required></label><label><span>Role</span><select name="role"><option value="user">User</option><option value="admin">Administrator</option></select></label></div><div class="check-grid">${profileOptions}</div><button class="button button-primary" type="submit">Create account</button></form>
    <section class="section-block"><div class="section-heading"><div><span class="eyebrow">ACCOUNTS</span><h2>Companion users</h2></div></div><div class="user-grid">${users}</div></section>
    <section class="section-block"><div class="section-heading"><div><span class="eyebrow">OPERATIONS</span><h2>Diagnostics and backups</h2></div><div><button class="button button-secondary" data-action="diagnostics-refresh">Run diagnostics</button><button class="button button-primary" data-action="backup-create">Create backup</button></div></div>${state.diagnostics ? `<pre class="diagnostic-output">${escapeHtml(safeJson(state.diagnostics))}</pre>` : ''}<div class="backup-list">${backups || '<p class="faint">No backups yet.</p>'}</div></section>
  </div>`
}

function formatBytes(value) {
  let bytes = Number(value || 0)
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let index = 0
  while (bytes >= 1024 && index < units.length - 1) { bytes /= 1024; index += 1 }
  return `${bytes >= 10 || index === 0 ? bytes.toFixed(0) : bytes.toFixed(1)} ${units[index]}`
}

function renderSettings() {
  const profiles = state.profiles.map(profile => `<article><span class="agent-color" style="background:${escapeAttr(profile.accent || '#8b5cf6')}"></span><div><strong>${escapeHtml(profile.label)}</strong><code>${escapeHtml(profile.slug)}</code></div><span class="${profile.configured ? 'configured' : 'missing'}">${profile.configured ? (profile.gateway_available ? 'Connected + live session' : 'Connected') : 'Not connected'}</span></article>`).join('')
  const devices = state.devices.map(device => `<div class="device-row"><div><strong>${escapeHtml(device.device_name || 'Unnamed device')}${device.current ? ' · this device' : ''}</strong><small>last used ${escapeHtml(relativeTime(device.last_used_at))}</small></div><button class="button button-sm button-danger" data-action="device-revoke" data-id="${escapeAttr(device.device_id)}">Sign out</button></div>`).join('')
  const theme = storage.get('hc.theme') || ''
  const pushLabel = state.push && state.push.subscribed ? 'Turn off on this device' : (state.push && state.push.supported ? 'Turn on' : 'Not supported in this browser')
  return `<div class="page">
    ${pageHeader('SETTINGS', LABELS.settings, 'Your account, sign-in, alerts and this app.')}
    <section class="section-block"><h2>Sign-in</h2>
      <div class="section-heading"><div><span class="eyebrow">PASSKEYS</span><h3>Passkeys</h3></div><button class="button button-primary" data-action="passkey-add" ${(state.passkeys && state.passkeys.available && (state.passkeys.credentials || []).length < 8) ? '' : 'disabled'}>Add passkey</button></div>
      <div class="device-list">${(state.passkeys && state.passkeys.credentials || []).map(item => `<div class="device-row"><div><strong>${escapeHtml(item.label || 'Passkey')}</strong><small>added ${escapeHtml(relativeTime(item.created_at))}${item.last_used_at ? ' · last used ' + escapeHtml(relativeTime(item.last_used_at)) : ' · never used'}</small></div><button class="button button-sm button-danger" data-action="passkey-remove" data-id="${escapeAttr(item.id)}">Remove</button></div>`).join('') || `<p class="faint">${(state.passkeys && state.passkeys.available) ? 'No passkeys yet. Add one from your phone or this browser for fingerprint or face sign-in.' : 'Passkeys need the public HTTPS address. Password sign-in always works.'}</p>`}</div>
      <form id="password-change-form" class="inline-form"><label><span>Current password</span><input name="current_password" type="password" required autocomplete="current-password"></label><label><span>New password</span><input name="new_password" type="password" required minlength="12" autocomplete="new-password"></label><button class="button button-primary" type="submit">Change and sign out</button></form>
      <div class="device-list">${devices || '<p class="faint">No active devices reported.</p>'}</div>
      <div class="button-row"><button class="button button-secondary" data-action="logout">Sign out</button><button class="button button-danger" data-action="logout-all">Sign out all devices</button></div>
    </section>
    <section class="section-block"><h2>Alerts</h2>
      <section class="settings-card"><header><span>◍</span><div><h3>Push notifications</h3><p>Get a notification when a task finishes or needs your OK — even when this app is closed.</p></div></header><button class="button button-secondary" data-action="push-toggle" ${(state.push && state.push.supported) ? '' : 'disabled'}>${pushLabel}</button></section>
    </section>
    <section class="section-block"><h2>This app</h2>
      <section class="settings-card"><header><span>⇩</span><div><h3>Install this app</h3><p>Add to your home screen for a full-screen app with its own icon.</p></div></header><button class="button button-secondary" data-action="install-pwa" ${state.installPrompt ? '' : 'disabled'}>${state.installPrompt ? 'Add to home screen' : 'Already installed or unavailable'}</button></section>
      <section class="settings-card"><header><span>◐</span><div><h3>Appearance</h3><p>Match your phone, or pick one.</p></div></header><select data-action="theme-change"><option value="" ${theme === '' ? 'selected' : ''}>System</option><option value="light" ${theme === 'light' ? 'selected' : ''}>Light</option><option value="dark" ${theme === 'dark' ? 'selected' : ''}>Dark</option></select></section>
    </section>
    <section class="section-block"><h2>Advanced</h2>
      <section class="settings-card wide"><header><span>⌁</span><div><h3>Bridge endpoint</h3><p>Only change this if you were told to.</p></div></header><form id="settings-bridge-form" class="endpoint-form"><input name="bridge" value="${escapeAttr(storage.get('bridgeUrl') || '')}" placeholder="Leave blank for this server"><button class="button button-primary" type="submit">Save and sign in again</button></form></section>
      <div class="settings-profile-list">${profiles}</div>
      <section class="about-card"><div class="brand"><span class="brand-mark">H</span><span class="brand-copy"><strong>Hermes Companion</strong><small>${escapeHtml(VERSION_LABEL)}</small></span></div><p>Private control plane for your assistants.</p><a href="${escapeAttr(endpoint('/api/health'))}" target="_blank" rel="noreferrer">Health check ↗</a></section>
    </section>
  </div>`
}

function currentPage() {
  if (state.route === '/projects') return renderProjects()
  if (state.route === '/chat') return renderChat()
  if (state.route === '/sessions') return renderSessions()
  if (state.route === '/automations') return renderAutomations()
  if (state.route === '/notifications') return renderNotifications()
  if (state.route === '/files') return renderFiles()
  if (state.route === '/prompts') return renderPrompts()
  if (state.route === '/gateway') return renderGateway()
  if (state.route === '/audit') return renderAudit()
  if (state.route === '/admin') return renderAdmin()
  if (state.route === '/settings') return renderSettings()
  return renderOverview()
}

function syncOffline() {
  document.querySelectorAll('.offline-banner').forEach(node => { node.hidden = navigator.onLine })
}

function render() {
  if (state.booting) return renderBoot()
  if (!state.user) return renderLogin()
  ROOT.innerHTML = shell(currentPage())
  if (state.route === '/chat') {
    scrollChat(false)
    const box = document.getElementById('chat-scroll')
    const workspace = document.querySelector('.chat-workspace')
    if (box && workspace) {
      const update = () => workspace.classList.toggle('not-at-bottom', box.scrollHeight - box.scrollTop - box.clientHeight > 120)
      box.addEventListener('scroll', update, { passive: true })
      update()
    }
  }
  syncOffline()
}

function updateChatDynamic() {
  const column = document.getElementById('message-column')
  if (column) column.innerHTML = renderChatMessages()
  const toolbar = document.getElementById('run-toolbar')
  if (toolbar) toolbar.innerHTML = runControls()
  const composer = document.getElementById('composer-form')
  if (composer) {
    const textarea = composer.querySelector('textarea')
    const send = composer.querySelector('button[type="submit"]')
    if (textarea) textarea.disabled = !permission('chat') || !state.currentSessionId || state.run?.status === 'waiting_for_approval'
    if (send) send.disabled = !permission('chat') || !state.currentSessionId || state.busy === 'send'
  }
  scrollChat(true)
}

function scrollChat(smooth = false) {
  const box = document.getElementById('chat-scroll')
  if (box) box.scrollTo({ top: box.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
}

async function login(form) {
  const data = new FormData(form)
  const bridge = sanitiseBridgeUrl(String(data.get('bridge') || ''))
  const email = String(data.get('email') || '').trim()
  const password = String(data.get('password') || '')
  storage.set('bridgeUrl', bridge)
  state.busy = 'login'; state.error = ''; render()
  try {
    const tokens = await apiFetch('/api/auth/login', {
      method: 'POST', body: JSON.stringify({ email, password, device_id: deviceId(), device_name: navigator.userAgent.slice(0,120) })
    }, { auth: false })
    saveTokens(tokens)
    await loadProfiles()
    await resolveHandoff()
    await loadRoute()
  } catch (error) {
    state.error = humanizeNetworkError(error)
    state.user = null
  } finally { state.busy = ''; render() }
}

function base64urlToBuffer(value) {
  const padding = '='.repeat((4 - (String(value).length % 4)) % 4)
  const base64 = (String(value) + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  const output = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) output[i] = raw.charCodeAt(i)
  return output.buffer
}

function bufferToBase64url(buffer) {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function publicKeyFromOptions(options) {
  const publicKey = { ...options }
  publicKey.challenge = base64urlToBuffer(publicKey.challenge)
  if (publicKey.user && publicKey.user.id) publicKey.user = { ...publicKey.user, id: base64urlToBuffer(publicKey.user.id) }
  if (Array.isArray(publicKey.allowCredentials)) publicKey.allowCredentials = publicKey.allowCredentials.map(item => ({ ...item, id: base64urlToBuffer(item.id) }))
  if (Array.isArray(publicKey.excludeCredentials)) publicKey.excludeCredentials = publicKey.excludeCredentials.map(item => ({ ...item, id: base64urlToBuffer(item.id) }))
  return publicKey
}

async function loginWithPasskey() {
  const form = document.getElementById('login-form')
  const data = form ? new FormData(form) : new FormData()
  const email = String(data.get('email') || '').trim()
  storage.set('bridgeUrl', String(data.get('bridge') || '').trim().replace(/\/+$/, ''))
  state.busy = 'login'; state.error = ''; render()
  try {
    const optionsPayload = await apiFetch('/api/auth/webauthn/login/options', {
      method: 'POST', body: JSON.stringify({ email }),
    }, { auth: false })
    const credential = await navigator.credentials.get({ publicKey: publicKeyFromOptions(optionsPayload.options.publicKey) })
    const response = {
      id: credential.id, rawId: bufferToBase64url(credential.rawId), type: credential.type,
      response: {
        clientDataJSON: bufferToBase64url(credential.response.clientDataJSON),
        authenticatorData: bufferToBase64url(credential.response.authenticatorData),
        signature: bufferToBase64url(credential.response.signature),
        userHandle: credential.response.userHandle ? bufferToBase64url(credential.response.userHandle) : null,
      },
    }
    const tokens = await apiFetch('/api/auth/webauthn/login', {
      method: 'POST', body: JSON.stringify({ token: optionsPayload.token, device_name: navigator.userAgent.slice(0, 120), response }),
    }, { auth: false })
    saveTokens(tokens)
    await loadProfiles()
    await resolveHandoff()
    await loadRoute()
  } catch (error) {
    state.error = error instanceof Error ? error.message : 'Passkey sign-in failed'
    state.user = null
  } finally { state.busy = ''; render() }
}

async function addPasskey() {
  if (!window.PublicKeyCredential || !navigator.credentials?.create) {
    toast('This browser cannot add a passkey. Use Safari on the phone, on the same address you signed in with.', 'error')
    return
  }
  try {
    const optionsPayload = await apiFetch('/api/auth/webauthn/register/options', { method: 'POST', body: '{}' })
    const publicKey = publicKeyFromOptions(optionsPayload.options.publicKey || optionsPayload.options)
    const credential = await navigator.credentials.create({ publicKey })
    if (!credential) throw new Error('Passkey was cancelled')
    const label = /iphone|ipad|android|mobile/i.test(navigator.userAgent) ? 'Phone passkey' : 'Device passkey'
    await apiFetch('/api/auth/webauthn/register', {
      method: 'POST', body: JSON.stringify({
        token: optionsPayload.token, label,
        response: {
          id: credential.id, rawId: bufferToBase64url(credential.rawId), type: credential.type,
          response: {
            clientDataJSON: bufferToBase64url(credential.response.clientDataJSON),
            attestationObject: bufferToBase64url(credential.response.attestationObject),
          },
        },
      }),
    })
    toast('Passkey added to this device', 'success')
    await loadSettingsData(); render()
  } catch (error) {
    const name = error && error.name
    if (name === 'NotAllowedError' || name === 'AbortError') {
      toast('Passkey was cancelled, or this screen cannot use Face ID / fingerprint. Try Safari (not a home-screen icon) if it keeps failing.', 'error')
      return
    }
    if (name === 'InvalidStateError') {
      toast('This device already has a passkey for this account.', 'info')
      return
    }
    toast(humanizeNetworkError(error), 'error')
  }
}

async function removePasskey(credentialId) {
  await apiFetch(`/api/auth/webauthn/${encodeURIComponent(credentialId)}`, { method: 'DELETE' })
  toast('Passkey removed', 'info')
  await loadSettingsData(); render()
}

async function logout() {
  const refresh = storage.get('refresh')
  try {
    await apiFetch('/api/auth/logout', { method: 'POST', body: JSON.stringify({ refresh_token: refresh || null }) })
  } catch { /* local logout must still complete */ }
  state.streamController?.abort()
  storage.clearAuth()
  state.user = null
  state.profiles = []
  state.run = null
  render()
}

async function loadProfiles() {
  const response = await apiFetch('/api/profiles')
  state.profiles = response.profiles || []
  const configured = state.profiles.filter(item => item.configured)
  if (!configured.some(item => item.slug === state.activeProfile)) {
    state.activeProfile = configured[0]?.slug || state.profiles[0]?.slug || 'default'
    storage.set('profile', state.activeProfile)
  }
}

async function loadOverview() {
  const [overview] = await Promise.all([
    apiFetch('/api/overview'),
    loadSessions().catch(() => undefined),
    loadSettingsData().catch(() => undefined),
  ])
  state.overview = overview
  state.unreadNotifications = Number(state.overview.unread_notifications || 0)
}
async function loadSessions() {
  const [payload, metadata] = await Promise.all([
    apiFetch(`/api/profiles/${encodeURIComponent(state.activeProfile)}/sessions?limit=250`),
    apiFetch(`/api/profiles/${encodeURIComponent(state.activeProfile)}/session-metadata`).catch(() => ({ metadata: [] }))
  ])
  state.sessions = listFromPayload(payload, ['sessions','items','data'])
  state.sessionMetadata = new Map((metadata.metadata || []).map(item => [String(item.session_id), item]))
  if (state.currentSessionId && !state.sessions.some(item => sessionId(item) === state.currentSessionId)) state.currentSessionId = ''
}
async function loadMessages() {
  if (!state.currentSessionId) { state.messages = []; return }
  const payload = await apiFetch(`/api/profiles/${encodeURIComponent(state.activeProfile)}/sessions/${encodeURIComponent(state.currentSessionId)}/messages?limit=500`)
  state.messages = listFromPayload(payload, ['messages','items','data'])
}
async function loadJobs() {
  const payload = await apiFetch(`/api/profiles/${encodeURIComponent(state.activeProfile)}/jobs`)
  state.jobs = listFromPayload(payload, ['jobs','items','data'])
}
async function loadAudit() {
  const payload = await apiFetch('/api/audit?limit=250')
  state.audit = payload.events || []
}

async function loadProjects() {
  const payload = await apiFetch('/api/projects')
  state.projects = payload.projects || []
  state.unreadNotifications = Number(payload.unread_notifications || 0)
}

async function loadNotifications() {
  const payload = await apiFetch('/api/notifications?limit=250')
  state.notifications = payload.notifications || []
  state.unreadNotifications = Number(payload.unread || 0)
}

async function loadFiles() {
  const payload = await apiFetch(`/api/files?profile=${encodeURIComponent(state.activeProfile)}&limit=250`)
  state.files = payload.files || []
  state.fileConfig = payload
}

async function loadPrompts() {
  const payload = await apiFetch('/api/prompts')
  state.prompts = payload.prompts || []
}

async function loadSettingsData() {
  const devices = await apiFetch('/api/auth/devices').catch(() => ({ devices: [] }))
  state.devices = devices.devices || []
  state.passkeys = await apiFetch('/api/auth/webauthn').catch(() => ({ available: false, credentials: [] }))
  await loadPushStatus()
}

function urlB64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  const output = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) output[i] = raw.charCodeAt(i)
  return output
}

async function loadPushStatus() {
  state.push = {
    supported: 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window,
    permission: 'Notification' in window ? Notification.permission : 'unavailable',
    subscribed: false,
  }
  try {
    if (state.push.supported) {
      const registration = await navigator.serviceWorker.getRegistration()
      if (registration && registration.pushManager) {
        const existing = await registration.pushManager.getSubscription()
        if (existing) state.push.subscribed = true
      }
    }
  } catch { /* offline or unsupported */ }
}

async function enablePush() {
  if (!state.push || !state.push.supported) { toast('Push is not supported in this browser', 'error'); return }
  const permission = await Notification.requestPermission()
  state.push.permission = permission
  if (permission !== 'granted') { toast('Notification permission denied', 'error'); render(); return }
  const keyPayload = await apiFetch('/api/push/key').catch(() => null)
  if (!keyPayload || !keyPayload.public_key) { toast('Push is not configured on the bridge', 'error'); return }
  const registration = await navigator.serviceWorker.ready
  const stale = await registration.pushManager.getSubscription()
  if (stale) await stale.unsubscribe().catch(() => undefined)
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlB64ToUint8Array(keyPayload.public_key),
  })
  const details = subscription.toJSON()
  await apiFetch('/api/push/subscribe', {
    method: 'POST',
    body: JSON.stringify({ endpoint: details.endpoint, p256dh: details.keys.p256dh, auth: details.keys.auth }),
  })
  toast('Push notifications enabled on this device', 'success')
  await loadPushStatus(); render()
}

async function disablePush() {
  try {
    const registration = await navigator.serviceWorker.getRegistration()
    if (registration && registration.pushManager) {
      const existing = await registration.pushManager.getSubscription()
      if (existing) {
        await apiFetch('/api/push/subscribe', { method: 'DELETE', body: JSON.stringify({ endpoint: existing.endpoint }) }).catch(() => undefined)
        await existing.unsubscribe().catch(() => undefined)
      }
    }
    toast('Push notifications disabled on this device', 'info')
  } catch (error) { toast(String(error.message || error), 'error') }
  await loadPushStatus(); render()
}

async function togglePush() {
  await (state.push && state.push.subscribed ? disablePush() : enablePush())
}

async function loadAdmin() {
  if (state.user?.role !== 'admin') return
  const [users, backups] = await Promise.all([
    apiFetch('/api/admin/users'),
    apiFetch('/api/backups')
  ])
  state.users = users.users || []
  state.backups = backups.backups || []
}

async function loadDiagnostics() {
  state.diagnostics = await apiFetch('/api/diagnostics')
}

async function refreshUnreadCount() {
  try {
    const payload = await apiFetch('/api/notifications?unread_only=true&limit=1')
    state.unreadNotifications = Number(payload.unread || 0)
  } catch { /* non-critical badge */ }
}

function flattenModels(payload) {
  const found = new Map()
  const walk = (value, provider = '') => {
    if (Array.isArray(value)) return value.forEach(item => walk(item, provider))
    if (!value || typeof value !== 'object') return
    const nextProvider = String(value.provider || value.provider_id || provider || '')
    const id = value.id || value.value || value.model || value.slug
    const likelyModel = id && (value.name || value.label || value.model || value.context_length || value.pricing)
    if (likelyModel && typeof id === 'string') {
      const label = String(value.label || value.name || id)
      const full = nextProvider && !String(id).includes(':') ? `${nextProvider}:${id}` : String(id)
      found.set(full, { id: full, label: nextProvider ? `${label} · ${nextProvider}` : label })
    }
    for (const child of Object.values(value)) if (child && typeof child === 'object') walk(child, nextProvider)
  }
  walk(payload)
  return [...found.values()].slice(0, 300)
}

async function loadModels() {
  try {
    const payload = await apiFetch(`/api/profiles/${encodeURIComponent(state.activeProfile)}/model-options`)
    state.models = flattenModels(payload)
  } catch { state.models = [] }
}

async function loadRoute() {
  if (!state.user) return
  state.loadingPage = true; state.error = ''; render()
  try {
    if (state.route === '/') await loadOverview()
    else if (state.route === '/projects') await loadProjects()
    else if (state.route === '/sessions') await loadSessions()
    else if (state.route === '/chat') {
      await Promise.all([loadSessions(), loadModels()])
      const query = new URLSearchParams(location.search)
      const requested = query.get('session')
      if (requested) state.currentSessionId = requested
      if (!state.currentSessionId) state.currentSessionId = storage.get(`session.${state.activeProfile}`) || sessionId(state.sessions[0])
      if (state.currentSessionId) {
        storage.set(`session.${state.activeProfile}`, state.currentSessionId)
        await loadMessages()
        await reconnectStoredRun()
      }
    } else if (state.route === '/automations') await loadJobs()
    else if (state.route === '/notifications') await loadNotifications()
    else if (state.route === '/files') await loadFiles()
    else if (state.route === '/prompts') await loadPrompts()
    else if (state.route === '/audit') await loadAudit()
    else if (state.route === '/admin') await loadAdmin()
    else if (state.route === '/settings') await loadSettingsData()
  } catch (error) {
    state.error = error instanceof Error ? error.message : 'Unable to load page'
    toast(state.error, 'error')
  } finally { state.loadingPage = false; render() }
}

async function navigate(path, { replace = false } = {}) {
  const route = normaliseRoute(path)
  if (replace) history.replaceState({}, '', route)
  else history.pushState({}, '', route)
  state.route = route
  state.mobileMenu = false
  await loadRoute()
}

async function changeProfile(slug) {
  const profile = state.profiles.find(item => item.slug === slug && item.configured)
  if (!profile || slug === state.activeProfile) return
  state.streamController?.abort()
  if (state.gatewayConnected) disconnectGateway()
  state.activeProfile = slug
  storage.set('profile', slug)
  state.currentSessionId = storage.get(`session.${slug}`) || ''
  state.sessions = []; state.messages = []; state.jobs = []; state.models = []
  clearRunState(false)
  await loadRoute()
}

async function createSession(title = '') {
  state.busy = 'session-create'; render()
  try {
    const payload = await apiFetch(`/api/profiles/${encodeURIComponent(state.activeProfile)}/sessions`, {
      method: 'POST', body: JSON.stringify(title ? { title } : {})
    })
    await loadSessions()
    const direct = payload?.session || payload?.data || payload
    const id = sessionId(direct) || sessionId(state.sessions[0])
    if (!id) throw new Error('Hermes did not return a session ID')
    state.currentSessionId = id
    storage.set(`session.${state.activeProfile}`, id)
    state.showSessionCreate = false
    history.pushState({}, '', '/chat')
    state.route = '/chat'
    await Promise.all([loadMessages(), loadModels()])
    toast('Session created', 'success')
  } finally { state.busy = ''; render() }
}

async function saveSessionMeta(id, meta) {
  const result = await apiFetch(`/api/profiles/${encodeURIComponent(state.activeProfile)}/session-metadata/${encodeURIComponent(id)}`, {
    method: 'PUT', body: JSON.stringify({ pinned: Boolean(meta.pinned), tags: meta.tags || [], note: meta.note || '' })
  })
  state.sessionMetadata.set(String(id), result)
  render()
}

async function toggleSessionPin(id) {
  const meta = sessionMeta(id)
  await saveSessionMeta(id, { ...meta, pinned: !meta.pinned })
  toast(meta.pinned ? 'Session unpinned' : 'Session pinned', 'success')
}

async function editSessionMeta(id) {
  const meta = sessionMeta(id)
  const result = await sheet({
    title: 'Tags and note',
    fields: [
      { name: 'tags', label: 'Tags (comma separated)', value: (meta.tags || []).join(', ') },
      { name: 'note', label: 'Private note', value: meta.note || '', type: 'textarea' },
    ],
    confirmLabel: 'Save',
  })
  if (result === null) return
  await saveSessionMeta(id, {
    ...meta,
    tags: result.tags.split(',').map(value => value.trim()).filter(Boolean),
    note: result.note.trim()
  })
  toast('Saved', 'success')
}

async function renameSession(id) {
  const current = state.sessions.find(item => sessionId(item) === id)
  const title = await ask('Rename conversation', sessionTitle(current), { label: 'Title', required: true })
  if (!title?.trim()) return
  await apiFetch(`/api/profiles/${encodeURIComponent(state.activeProfile)}/sessions/${encodeURIComponent(id)}`, {
    method: 'PATCH', body: JSON.stringify({ title: title.trim() })
  })
  await loadSessions(); render(); toast('Session renamed', 'success')
}

async function forkSession(id) {
  const payload = await apiFetch(`/api/profiles/${encodeURIComponent(state.activeProfile)}/sessions/${encodeURIComponent(id)}/fork`, { method: 'POST', body: '{}' })
  await loadSessions()
  const direct = payload?.session || payload?.data || payload
  const forked = sessionId(direct) || sessionId(state.sessions[0])
  if (forked) { state.currentSessionId = forked; storage.set(`session.${state.activeProfile}`, forked); await navigate('/chat') }
  toast('Session branch created', 'success')
}

async function deleteSession(id) {
  const current = state.sessions.find(item => sessionId(item) === id)
  if (!await okay('Delete this conversation?', `“${sessionTitle(current)}” will be removed for everyone. This cannot be undone.`, { confirmLabel: 'Delete', danger: true })) return
  await apiFetch(`/api/profiles/${encodeURIComponent(state.activeProfile)}/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' })
  if (state.currentSessionId === id) state.currentSessionId = ''
  await loadSessions(); render(); toast('Session deleted', 'success')
}

async function sessionMenu(id) {
  const meta = sessionMeta(id)
  const options = [
    { value: 'open', label: 'Open' },
    { value: 'pin', label: meta.pinned ? 'Unpin' : 'Pin to top' },
    { value: 'meta', label: 'Tags and note' },
    ...(permission('session_write') ? [{ value: 'rename', label: 'Rename' }, { value: 'fork', label: 'Duplicate (branch)' }, { value: 'delete', label: 'Delete…', danger: true }] : []),
  ]
  const current = state.sessions.find(item => sessionId(item) === id)
  const choice = await sheet({ title: sessionTitle(current), fields: [{ name: 'choice', type: 'list', options }], cancelLabel: 'Close' })
  if (!choice) return
  const handlers = { open: () => openSession(id), pin: () => toggleSessionPin(id), meta: () => editSessionMeta(id), rename: () => renameSession(id), fork: () => forkSession(id), delete: () => deleteSession(id) }
  await handlers[choice]?.()
}

async function openNotification(id) {
  const item = state.notifications.find(n => n.id === id)
  if (!item) return
  const meta = item.metadata || {}
  if (item.profile && item.profile !== state.activeProfile && state.profiles.some(p => p.slug === item.profile && p.configured)) {
    await changeProfile(item.profile)
  }
  if (meta.session_id) await openSession(meta.session_id)
  else await navigate('/chat')
  if (!item.read_at) await notificationRead(item.id, true)
}

async function openSession(id) {
  if (!id) return
  state.currentSessionId = id
  storage.set(`session.${state.activeProfile}`, id)
  state.chatDrawer = false
  const url = new URL(location.href)
  url.pathname = '/chat'; url.search = ''
  history.pushState({}, '', url)
  state.route = '/chat'
  state.loadingPage = true; render()
  try {
    await Promise.all([loadMessages(), state.models.length ? Promise.resolve() : loadModels()])
    await reconnectStoredRun()
  } catch (error) { toast(error instanceof Error ? error.message : 'Unable to load session', 'error') }
  finally { state.loadingPage = false; render() }
}

function activeRunStorageKey() { return `activeRun.${state.activeProfile}.${state.currentSessionId}` }
function persistRun() {
  if (!state.run || !state.currentSessionId) return
  storage.setJson(activeRunStorageKey(), {
    profile: state.activeProfile, session_id: state.currentSessionId,
    run_id: state.run.run_id, status: state.run.status, last_event_id: state.lastEventId
  })
}
function clearRunState(clearLive = true) {
  state.streamController?.abort(); state.streamController = null
  if (state.currentSessionId) storage.remove(activeRunStorageKey())
  state.run = null; state.approval = null; state.streamError = ''; state.lastEventId = ''
  if (clearLive) { state.liveText = ''; state.toolEvents = [] }
}

function parseSseBlock(block) {
  let type = 'message'; let id = ''; const data = []
  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue
    const colon = line.indexOf(':')
    const field = colon >= 0 ? line.slice(0,colon) : line
    const value = colon >= 0 ? line.slice(colon+1).replace(/^ /,'') : ''
    if (field === 'event') type = value
    else if (field === 'id') id = value
    else if (field === 'data') data.push(value)
  }
  if (!data.length && type === 'message') return null
  const raw = data.join('\n')
  let parsed = raw
  if (raw) { try { parsed = JSON.parse(raw) } catch { /* text event */ } }
  if (parsed && typeof parsed === 'object' && parsed.event && type === 'message') type = String(parsed.event)
  return { type, id, data: parsed }
}

async function streamSse(path, onMessage, signal, lastEventId = '') {
  const connect = async () => {
    const headers = { Accept: 'text/event-stream', Authorization: `Bearer ${storage.get('access') || ''}` }
    if (lastEventId) headers['Last-Event-ID'] = lastEventId
    return fetch(endpoint(path), { headers, signal })
  }
  let response = await connect()
  if (response.status === 401 && await refreshAccess()) response = await connect()
  if (!response.ok || !response.body) throw new Error(`Stream failed (${response.status})`)
  const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() || ''
    for (const block of blocks) { const message = parseSseBlock(block); if (message) onMessage(message) }
  }
  if (buffer.trim()) { const message = parseSseBlock(buffer); if (message) onMessage(message) }
}

function terminalRun(type, data) {
  const status = type.replace(/^run\./,'')
  browserNotify(`Hermes run ${status}`, activeProfile()?.label || state.activeProfile)
  void refreshUnreadCount()
  if (data?.output && !state.liveText) state.liveText = String(data.output)
  if (state.run) state.run.status = status
  persistRun(); updateChatDynamic()
  storage.remove(activeRunStorageKey())
  setTimeout(async () => {
    try { await loadMessages(); await loadSessions() } catch { /* keep live fallback */ }
    state.run = null; state.approval = null; state.streamController = null
    state.streamError = ''; state.toolEvents = []; state.liveText = ''
    render()
  }, 250)
}

function handleRunEvent(message) {
  const data = message.data && typeof message.data === 'object' ? message.data : { text: message.data }
  const type = message.type === 'message' && data.event ? String(data.event) : message.type
  if (message.id) state.lastEventId = message.id
  if (state.run && data.run_id) state.run.run_id = data.run_id
  if (type === 'assistant.delta' || type === 'message.delta') state.liveText += String(data.delta ?? data.text ?? '')
  else if (type === 'approval.request') {
    state.approval = data; if (state.run) state.run.status = 'waiting_for_approval'
    browserNotify('Hermes approval required', String(data.description || data.command || activeProfile()?.label || ''))
    void refreshUnreadCount()
  } else if (type === 'tool.started' || type === 'tool.completed' || type === 'subagent.start' || type === 'subagent.complete' || type === 'reasoning.available') {
    state.toolEvents.push({ id: `${Date.now()}-${Math.random()}`, event: type, ...data })
  } else if (type === 'run.queued' || type === 'run.running' || type === 'run.waiting_for_approval') {
    if (state.run) state.run.status = type.replace('run.','')
  } else if (['run.completed','run.failed','run.cancelled','run.interrupted'].includes(type)) {
    terminalRun(type, data); return
  } else if (type === 'bridge.error' || type === 'bridge.timeout') {
    state.streamError = String(data.detail || 'Run stream ended')
  }
  persistRun(); updateChatDynamic()
}

async function subscribeRun() {
  if (!state.run?.run_id) return
  state.streamController?.abort()
  const controller = new AbortController(); state.streamController = controller; state.streamError = ''
  updateChatDynamic()
  try {
    await streamSse(`/api/profiles/${encodeURIComponent(state.activeProfile)}/runs/${encodeURIComponent(state.run.run_id)}/events`, handleRunEvent, controller.signal, state.lastEventId)
    if (state.run && !['completed','failed','cancelled','interrupted'].includes(state.run.status)) {
      state.streamError = 'The event stream disconnected. The Hermes run may still be active.'
      updateChatDynamic()
    }
  } catch (error) {
    if (error?.name !== 'AbortError' && state.run) {
      state.streamError = error instanceof Error ? error.message : 'Run stream disconnected'
      updateChatDynamic()
    }
  }
}

async function reconnectStoredRun() {
  const saved = storage.json(activeRunStorageKey())
  if (!saved?.run_id) return
  try {
    const status = await apiFetch(`/api/profiles/${encodeURIComponent(state.activeProfile)}/runs/${encodeURIComponent(saved.run_id)}`)
    if (['completed','failed','cancelled','interrupted'].includes(status.status)) {
      storage.remove(activeRunStorageKey()); return
    }
    state.run = status; state.lastEventId = saved.last_event_id || ''; state.approval = status.approval || null
    void subscribeRun()
  } catch { storage.remove(activeRunStorageKey()) }
}

async function startRun(text) {
  if (!text.trim() || !state.currentSessionId || state.run) return
  state.busy = 'send'
  state.messages.push({ role: 'user', content: text, created_at: Date.now() })
  state.liveText = ''; state.toolEvents = []; state.approval = null; state.streamError = ''
  render()
  try {
    const idempotency = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`
    const body = { input: text, session_id: state.currentSessionId, idempotency_key: idempotency }
    if (state.selectedModel) body.model = state.selectedModel
    const result = await apiFetch(`/api/profiles/${encodeURIComponent(state.activeProfile)}/runs`, { method: 'POST', body: JSON.stringify(body), headers: { 'Idempotency-Key': idempotency } })
    if (!result?.run_id) throw new Error('Hermes did not return a run ID')
    state.run = { ...result, status: result.status || 'queued' }
    persistRun(); updateChatDynamic(); void subscribeRun()
  } catch (error) {
    state.streamError = error instanceof Error ? error.message : 'Unable to start run'
    toast(state.streamError, 'error')
  } finally { state.busy = ''; updateChatDynamic() }
}

async function runAction(action, body = {}) {
  if (!state.run?.run_id) return
  const result = await apiFetch(`/api/profiles/${encodeURIComponent(state.activeProfile)}/runs/${encodeURIComponent(state.run.run_id)}/${action}`, { method: 'POST', body: JSON.stringify(body) })
  return result
}

async function stopRun() {
  if (!await okay('Stop the current task?', 'The assistant will stop what it is doing.', { confirmLabel: 'Stop', danger: true })) return
  await runAction('stop'); if (state.run) state.run.status = 'stopping'; updateChatDynamic(); toast('Stop requested', 'success')
}
async function steerRun() {
  const input = await ask('Steer the assistant', '', { label: 'What should it do differently?', type: 'textarea', confirmLabel: 'Send' })
  if (!input?.trim()) return
  await runAction('steer', { input: input.trim() }); toast('Steer queued', 'success')
}
async function approveRun(choice) {
  await runAction('approval', { choice, resolve_all: false })
  state.approval = null; if (state.run) state.run.status = choice === 'deny' ? 'running' : 'running'
  updateChatDynamic(); toast(choice === 'once' ? 'Approved once' : 'Denied', choice === 'once' ? 'success' : 'info')
}

async function createJob(form) {
  const data = new FormData(form)
  const body = { name: String(data.get('name') || '').trim(), schedule: String(data.get('schedule') || '').trim(), prompt: String(data.get('prompt') || '').trim(), enabled: true }
  state.busy = 'job-create'; render()
  try {
    await apiFetch(`/api/profiles/${encodeURIComponent(state.activeProfile)}/jobs`, { method: 'POST', body: JSON.stringify(body) })
    state.showJobCreate = false; await loadJobs(); toast('Automation created', 'success')
  } finally { state.busy = ''; render() }
}

async function jobAction(id, action, body = {}) {
  await apiFetch(`/api/profiles/${encodeURIComponent(state.activeProfile)}/jobs/${encodeURIComponent(id)}/${action}`, { method: 'POST', body: JSON.stringify(body) })
  await loadJobs(); render(); toast(`Job ${action} accepted`, 'success')
}

async function deleteJob(id) {
  if (!await okay('Delete this scheduled task?', '', { confirmLabel: 'Delete', danger: true })) return
  await apiFetch(`/api/profiles/${encodeURIComponent(state.activeProfile)}/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' })
  await loadJobs(); render(); toast('Automation deleted', 'success')
}


async function authenticatedResponse(path, init = {}, retry = true) {
  const headers = new Headers(init.headers || {})
  const access = storage.get('access')
  if (access) headers.set('Authorization', `Bearer ${access}`)
  let response = await fetch(endpoint(path), { ...init, headers })
  if (response.status === 401 && retry && await refreshAccess()) return authenticatedResponse(path, init, false)
  if (!response.ok) throw new ApiError(response.status, await parseError(response))
  return response
}

async function downloadProtected(path, filename) {
  const response = await authenticatedResponse(path)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename || 'download'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

async function notificationRead(id, read) {
  await apiFetch(`/api/notifications/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ read }) })
  await loadNotifications(); render()
}

async function notificationDelete(id) {
  await apiFetch(`/api/notifications/${encodeURIComponent(id)}`, { method: 'DELETE' })
  await loadNotifications(); render()
}

async function notificationsReadAll() {
  await apiFetch('/api/notifications/read-all', { method: 'POST', body: '{}' })
  await loadNotifications(); render(); toast('Notifications marked read', 'success')
}

async function requestNotificationPermission() {
  if (!('Notification' in window)) throw new Error('Browser notifications are unavailable')
  const result = await Notification.requestPermission()
  toast(`Browser notification permission: ${result}`, result === 'granted' ? 'success' : 'info')
}

function browserNotify(title, body = '') {
  if ('Notification' in window && Notification.permission === 'granted') {
    try { new Notification(title, { body, icon: '/icon-192.png', tag: title }) } catch { /* best effort */ }
  }
}

async function uploadFile(form) {
  const data = new FormData(form)
  const file = data.get('file')
  if (!(file instanceof File) || !file.size) throw new Error('Choose a file first')
  state.busy = 'file-upload'; render()
  try {
    const response = await authenticatedResponse('/api/files', { method: 'POST', body: data })
    const item = await response.json()
    await loadFiles(); render()
    await navigator.clipboard?.writeText(item.hermes_path).catch(() => undefined)
    toast('File staged; Hermes path copied when clipboard permission allowed', 'success')
  } finally { state.busy = ''; render() }
}

async function deleteFile(id) {
  if (!await okay('Delete this file?', '', { confirmLabel: 'Delete', danger: true })) return
  await apiFetch(`/api/files/${encodeURIComponent(id)}`, { method: 'DELETE' })
  await loadFiles(); render(); toast('File deleted', 'success')
}

async function createPrompt(form) {
  const data = new FormData(form)
  await apiFetch('/api/prompts', { method: 'POST', body: JSON.stringify({
    title: String(data.get('title') || '').trim(),
    profile: String(data.get('profile') || '').trim() || null,
    prompt: String(data.get('prompt') || '').trim()
  }) })
  form.reset(); await loadPrompts(); render(); toast('Prompt saved', 'success')
}

async function editPrompt(id) {
  const item = state.prompts.find(prompt => prompt.id === id)
  if (!item) return
  const result = await sheet({
    title: 'Edit saved prompt',
    fields: [
      { name: 'title', label: 'Title', value: item.title, required: true },
      { name: 'prompt', label: 'Prompt', value: item.prompt, type: 'textarea' },
      { name: 'profile', label: 'Assistant', type: 'select', value: item.profile || '', options: [{ value: '', label: 'All assistants' }, ...state.profiles.map(p => ({ value: p.slug, label: p.label }))] },
    ],
  })
  if (result === null) return
  await apiFetch(`/api/prompts/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify({
    title: result.title.trim(), prompt: result.prompt.trim(), profile: result.profile.trim() || null
  }) })
  await loadPrompts(); render(); toast('Prompt updated', 'success')
}

async function deletePrompt(id) {
  if (!await okay('Delete this saved prompt?', '', { confirmLabel: 'Delete', danger: true })) return
  await apiFetch(`/api/prompts/${encodeURIComponent(id)}`, { method: 'DELETE' })
  await loadPrompts(); render(); toast('Prompt deleted', 'success')
}

async function usePrompt(id) {
  const item = state.prompts.find(prompt => prompt.id === id)
  if (!item) return
  if (item.profile && item.profile !== state.activeProfile) await changeProfile(item.profile)
  state.composerDraft = item.prompt
  await navigate('/chat')
  requestAnimationFrame(() => document.querySelector('#composer-form textarea')?.focus())
}

async function createAdminUser(form) {
  const data = new FormData(form)
  const profiles = data.getAll('profiles').map(String)
  await apiFetch('/api/admin/users', { method: 'POST', body: JSON.stringify({
    email: String(data.get('email') || '').trim(), password: String(data.get('password') || ''),
    role: String(data.get('role') || 'user'), profiles
  }) })
  form.reset(); await loadAdmin(); render(); toast('Account created', 'success')
}

async function editAdminUser(id) {
  const user = state.users.find(item => item.id === id)
  if (!user) return
  const result = await sheet({
    title: 'Edit access',
    fields: [
      { name: 'profiles', label: 'Assistants (comma-separated slugs)', value: (user.profiles || []).join(', ') },
      { name: 'role', label: 'Role', type: 'select', value: user.role, options: [{ value: 'user', label: 'User' }, { value: 'admin', label: 'Admin' }] },
      { name: 'active', label: 'Status', type: 'select', value: user.active ? '1' : '0', options: [{ value: '1', label: 'Active' }, { value: '0', label: 'Disabled' }] },
    ],
  })
  if (result === null) return
  await apiFetch(`/api/admin/users/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({
    role: result.role.trim(), active: result.active === '1', profiles: result.profiles.split(',').map(value => value.trim()).filter(Boolean)
  }) })
  await loadAdmin(); render(); toast('Account updated', 'success')
}

async function resetAdminPassword(id) {
  const password = await ask('New password', '', { label: 'Password (min 12 characters)', type: 'password', confirmLabel: 'Reset' })
  if (!password) return
  await apiFetch(`/api/admin/users/${encodeURIComponent(id)}/password`, { method: 'POST', body: JSON.stringify({ password }) })
  toast('Password reset and existing sessions revoked', 'success')
}

async function deleteAdminUser(id) {
  if (!await okay('Delete this account?', 'This cannot be undone.', { confirmLabel: 'Delete', danger: true })) return
  await apiFetch(`/api/admin/users/${encodeURIComponent(id)}`, { method: 'DELETE' })
  await loadAdmin(); render(); toast('Account deleted', 'success')
}

async function createBackup() {
  const label = await ask('Backup label', 'manual', { label: 'Label' })
  if (label === null) return
  await apiFetch('/api/backups', { method: 'POST', body: JSON.stringify({ label }) })
  await loadAdmin(); render(); toast('Redacted backup created', 'success')
}

async function deleteBackup(name) {
  if (!await okay('Delete this backup?', String(name || ''), { confirmLabel: 'Delete', danger: true })) return
  await apiFetch(`/api/backups/${encodeURIComponent(name)}`, { method: 'DELETE' })
  await loadAdmin(); render(); toast('Backup deleted', 'success')
}

async function revokeDevice(id) {
  if (!await okay('Sign this device out?', '', { confirmLabel: 'Sign out', danger: true })) return
  const result = await apiFetch(`/api/auth/devices/${encodeURIComponent(id)}`, { method: 'DELETE' })
  if (result.current_device) {
    storage.clearAuth(); state.user = null; render(); return
  }
  await loadSettingsData(); render(); toast('Device revoked', 'success')
}

async function changePassword(form) {
  const data = new FormData(form)
  await apiFetch('/api/auth/password', { method: 'POST', body: JSON.stringify({
    current_password: String(data.get('current_password') || ''),
    new_password: String(data.get('new_password') || '')
  }) })
  storage.clearAuth(); state.user = null; render(); toast('Password changed. Sign in again.', 'success')
}

function gatewayWsUrl(path) {
  const url = new URL(endpoint(path), location.href)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}

function gatewaySend(frame) {
  if (!state.gatewaySocket || state.gatewaySocket.readyState !== WebSocket.OPEN) throw new Error('Live gateway is not connected')
  state.gatewaySocket.send(JSON.stringify(frame))
}

function gatewayRpc(method, params = {}, timeout = 30_000) {
  const id = state.gatewayNextId++
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      state.gatewayPending.delete(String(id)); reject(new Error(`${method} timed out`))
    }, timeout)
    state.gatewayPending.set(String(id), { resolve, reject, timer, method })
    gatewaySend({ jsonrpc: '2.0', id, method, params })
  })
}

function gatewayPushEvent(type, payload = {}) {
  state.gatewayEvents.push({ type, payload, summary: payload.preview || payload.tool || payload.status || payload.message || '' })
  if (state.gatewayEvents.length > 300) state.gatewayEvents.splice(0, state.gatewayEvents.length - 300)
}

function gatewayApplySnapshot(result) {
  state.gatewaySessionId = String(result?.session_id || '')
  state.gatewayStoredSessionId = String(result?.stored_session_id || result?.resumed || '')
  state.gatewayMessages = Array.isArray(result?.messages) ? result.messages : []
  if (result?.inflight?.user) state.gatewayMessages.push({ role: 'user', content: result.inflight.user })
  if (result?.inflight?.assistant) state.gatewayMessages.push({ role: 'assistant', content: result.inflight.assistant })
  state.gatewayRequests = Array.isArray(result?.open_requests) ? result.open_requests : []
}

function handleGatewayFrame(frame) {
  if (frame && Object.prototype.hasOwnProperty.call(frame, 'id') && !frame.method) {
    const pending = state.gatewayPending.get(String(frame.id))
    if (pending) {
      clearTimeout(pending.timer); state.gatewayPending.delete(String(frame.id))
      if (frame.error) pending.reject(new Error(frame.error.message || 'Gateway RPC failed'))
      else pending.resolve(frame.result)
    }
    return
  }
  if (frame?.method === 'event') {
    const type = String(frame.params?.type || 'event')
    const payload = frame.params?.payload || {}
    gatewayPushEvent(type, payload)
    if (type === 'message.delta' || type === 'reasoning.delta') {
      const delta = String(payload.delta || payload.text || payload.content || '')
      let last = state.gatewayMessages[state.gatewayMessages.length - 1]
      if (!last || last.role !== 'assistant' || !last._streaming) {
        last = { role: 'assistant', content: '', _streaming: true }
        state.gatewayMessages.push(last)
      }
      last.content += delta
    } else if (type === 'message.complete') {
      const last = state.gatewayMessages[state.gatewayMessages.length - 1]
      if (last?._streaming) delete last._streaming
      if (payload.message && typeof payload.message === 'object') state.gatewayMessages.push(payload.message)
    } else if (type === 'request.cancel') {
      const requestId = String(payload.id || '')
      state.gatewayRequests = state.gatewayRequests.filter(item => String(item.id) !== requestId)
    } else if (['turn.completed', 'turn.complete', 'turn.failed', 'turn.interrupted'].includes(type)) {
      browserNotify(`Hermes ${type.replace('turn.', '')}`, activeProfile()?.label || state.activeProfile)
    }
    render()
    requestAnimationFrame(() => document.querySelector('.gateway-transcript')?.scrollTo({ top: 999999 }))
    return
  }
  if (frame?.method && Object.prototype.hasOwnProperty.call(frame, 'id')) {
    state.gatewayRequests = [...state.gatewayRequests.filter(item => String(item.id) !== String(frame.id)), frame]
    browserNotify('Hermes needs input', frame.method)
    render()
  }
}

async function connectGateway() {
  if (state.gatewayConnected) return disconnectGateway()
  const ticket = await apiFetch(`/api/gateway/${encodeURIComponent(state.activeProfile)}/ticket`, { method: 'POST', body: '{}' })
  const socket = new WebSocket(gatewayWsUrl(ticket.path))
  state.gatewaySocket = socket
  state.gatewayProfile = state.activeProfile
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Gateway connection timed out')), 12_000)
    socket.addEventListener('open', () => { clearTimeout(timer); resolve() }, { once: true })
    socket.addEventListener('error', () => { clearTimeout(timer); reject(new Error('Gateway connection failed')) }, { once: true })
  })
  state.gatewayConnected = true
  socket.addEventListener('message', event => {
    String(event.data).split(/\r?\n/).filter(Boolean).forEach(line => {
      try { handleGatewayFrame(JSON.parse(line)) } catch { gatewayPushEvent('companion.parse_error', { message: 'Invalid JSON frame' }) }
    })
  })
  socket.addEventListener('close', () => {
    state.gatewayConnected = false; state.gatewaySocket = null
    for (const pending of state.gatewayPending.values()) { clearTimeout(pending.timer); pending.reject(new Error('Gateway disconnected')) }
    state.gatewayPending.clear(); render()
  })
  socket.addEventListener('error', () => toast('Live gateway transport error', 'error'))
  render()
  await gatewayRpc('client.capabilities', { server_requests: true }).catch(() => undefined)
  toast('Live Hermes gateway connected', 'success')
}

function disconnectGateway() {
  state.gatewaySocket?.close(1000, 'Operator disconnected')
  state.gatewaySocket = null; state.gatewayConnected = false; state.gatewaySessionId = ''
  state.gatewayRequests = []; render()
}

async function gatewayNewSession() {
  const title = await ask('Live session title', 'Companion live session', { label: 'Title' })
  if (title === null) return
  const result = await gatewayRpc('session.create', { profile: state.activeProfile, source: 'hermes-companion', title: title.trim() || undefined })
  gatewayApplySnapshot(result); render()
}

async function gatewayResumeSession() {
  const id = await ask('Resume a conversation', state.currentSessionId || '', { label: 'Conversation ID or title' })
  if (!id?.trim()) return
  const result = await gatewayRpc('session.resume', { profile: state.activeProfile, session_id: id.trim(), eager_build: true })
  gatewayApplySnapshot(result); render()
}

async function gatewayListSessions() {
  const result = await gatewayRpc('session.list', { profile: state.activeProfile, limit: 50 })
  const rows = result?.sessions || []
  const chosen = rows.length
    ? await sheet({ title: 'Resume a conversation', fields: [{ name: 'id', label: 'Conversation', type: 'select', options: rows.map(item => ({ value: item.id, label: item.title || item.id })) }], confirmLabel: 'Resume' })
    : null
  if (chosen?.trim()) {
    const resumed = await gatewayRpc('session.resume', { profile: state.activeProfile, session_id: chosen.trim(), eager_build: true })
    gatewayApplySnapshot(resumed); render()
  }
}

async function gatewaySubmit(text) {
  if (!text.trim()) return
  state.gatewayMessages.push({ role: 'user', content: text.trim() })
  render()
  await gatewayRpc('prompt.submit', { profile: state.activeProfile, session_id: state.gatewaySessionId, text: text.trim() }, 120_000)
}

async function gatewayInterrupt() {
  await gatewayRpc('session.interrupt', { profile: state.activeProfile, session_id: state.gatewaySessionId })
  toast('Interrupt requested', 'success')
}

function gatewayAnswer(id, result) {
  gatewaySend({ jsonrpc: '2.0', id, result })
  state.gatewayRequests = state.gatewayRequests.filter(item => String(item.id) !== String(id))
  render()
}

function gatewayReject(id) {
  gatewaySend({ jsonrpc: '2.0', id, error: { code: -32601, message: 'Unsupported by Hermes Companion' } })
  state.gatewayRequests = state.gatewayRequests.filter(item => String(item.id) !== String(id))
  render()
}

async function resolveHandoff() {
  const query = new URLSearchParams(location.search)
  let profile = query.get('profile'); let session = query.get('session')
  const token = query.get('handoff')
  if (token) {
    try {
      const resolved = await apiFetch(`/api/handoff/${encodeURIComponent(token)}`)
      profile = resolved.profile; session = resolved.session_id
    } catch (error) { toast(error instanceof Error ? error.message : 'Handoff failed', 'error') }
  }
  if (profile && session && state.profiles.some(item => item.slug === profile && item.configured)) {
    state.activeProfile = profile; storage.set('profile', profile)
    state.currentSessionId = session; storage.set(`session.${profile}`, session)
    state.route = '/chat'; history.replaceState({}, '', '/chat')
  }
}

async function refreshCurrent() { await loadRoute() }

ROOT.addEventListener('click', async event => {
  const more = event.target.closest('[data-more]')
  if (more) { event.preventDefault(); await openMoreSheet(); return }
  const nav = event.target.closest('[data-nav]')
  if (nav) { event.preventDefault(); await navigate(nav.dataset.nav); return }
  const fileDownload = event.target.closest('[data-file-download]')
  if (fileDownload) { event.preventDefault(); await downloadProtected(`/api/files/${encodeURIComponent(fileDownload.dataset.fileDownload)}/download`, fileDownload.getAttribute('download') || 'hermes-file'); return }
  const backupDownload = event.target.closest('[data-backup-download]')
  if (backupDownload) { event.preventDefault(); await downloadProtected(`/api/backups/${encodeURIComponent(backupDownload.dataset.backupDownload)}`, backupDownload.dataset.backupDownload); return }
  const target = event.target.closest('[data-action]')
  if (!target) return
  const action = target.dataset.action
  try {
    if (action === 'mobile-menu') { state.mobileMenu = true; render() }
    else if (action === 'mobile-close') { state.mobileMenu = false; render() }
    else if (action === 'logout') await logout()
    else if (action === 'refresh') await refreshCurrent()
    else if (action === 'open-profile-chat') { await changeProfile(target.dataset.profile); await navigate('/chat') }
    else if (action === 'toggle-session-create') { state.showSessionCreate = !state.showSessionCreate; render() }
    else if (action === 'quick-new-session') { const title = await ask(LABELS.newSession, '', { label: 'Title' }); if (title !== null) await createSession(title.trim()) }
    else if (action === 'open-session') await openSession(target.dataset.session)
    else if (action === 'toggle-session-pin') await toggleSessionPin(target.dataset.session)
    else if (action === 'edit-session-meta') await editSessionMeta(target.dataset.session)
    else if (action === 'rename-session') await renameSession(target.dataset.session)
    else if (action === 'fork-session') await forkSession(target.dataset.session)
    else if (action === 'delete-session') await deleteSession(target.dataset.session)
    else if (action === 'session-menu') await sessionMenu(target.dataset.session)
    else if (action === 'chat-drawer-open') { state.chatDrawer = true; render() }
    else if (action === 'chat-drawer-close') { state.chatDrawer = false; render() }
    else if (action === 'run-stop') await stopRun()
    else if (action === 'run-steer') await steerRun()
    else if (action === 'run-approve') await approveRun('once')
    else if (action === 'run-deny') await approveRun('deny')
    else if (action === 'run-reconnect') void subscribeRun()
    else if (action === 'scroll-bottom') { const el = document.getElementById('chat-scroll'); if (el) el.scrollTop = el.scrollHeight }
    else if (action === 'toggle-job-create') { state.showJobCreate = !state.showJobCreate; render() }
    else if (action === 'job-run') await jobAction(target.dataset.job, 'run')
    else if (action === 'job-toggle') await jobAction(target.dataset.job, target.dataset.paused === '1' ? 'resume' : 'pause')
    else if (action === 'job-delete') await deleteJob(target.dataset.job)
    else if (action === 'project-session') { await changeProfile(target.dataset.profile); await openSession(target.dataset.session) }
    else if (action === 'notification-open') await openNotification(target.dataset.id)
    else if (action === 'notification-read') await notificationRead(target.dataset.id, target.dataset.read === '1')
    else if (action === 'notification-delete') await notificationDelete(target.dataset.id)
    else if (action === 'notifications-read-all') await notificationsReadAll()
    else if (action === 'notifications-permission') await requestNotificationPermission()
    else if (action === 'push-toggle') await togglePush()
    else if (action === 'passkey-login') await loginWithPasskey()
    else if (action === 'passkey-add') await addPasskey()
    else if (action === 'passkey-remove') await removePasskey(target.dataset.id)
    else if (action === 'file-copy') { await navigator.clipboard.writeText(target.dataset.path || ''); toast('Hermes path copied', 'success') }
    else if (action === 'file-delete') await deleteFile(target.dataset.id)
    else if (action === 'prompt-use') await usePrompt(target.dataset.id)
    else if (action === 'prompt-edit') await editPrompt(target.dataset.id)
    else if (action === 'prompt-delete') await deletePrompt(target.dataset.id)
    else if (action === 'gateway-toggle') await connectGateway()
    else if (action === 'gateway-list') await gatewayListSessions()
    else if (action === 'gateway-new') await gatewayNewSession()
    else if (action === 'gateway-resume') await gatewayResumeSession()
    else if (action === 'gateway-interrupt') await gatewayInterrupt()
    else if (action === 'gateway-answer') gatewayAnswer(target.dataset.request, { choice: target.dataset.choice })
    else if (action === 'gateway-reject') gatewayReject(target.dataset.request)
    else if (action === 'admin-edit') await editAdminUser(target.dataset.id)
    else if (action === 'admin-reset-password') await resetAdminPassword(target.dataset.id)
    else if (action === 'admin-delete') await deleteAdminUser(target.dataset.id)
    else if (action === 'diagnostics-refresh') { await loadDiagnostics(); render() }
    else if (action === 'backup-create') await createBackup()
    else if (action === 'backup-delete') await deleteBackup(target.dataset.name)
    else if (action === 'device-revoke') await revokeDevice(target.dataset.id)
    else if (action === 'logout-all') { if (await okay('Sign out every device?', '', { confirmLabel: 'Sign out', danger: true })) { await apiFetch('/api/auth/logout-all', { method: 'POST', body: '{}' }); storage.clearAuth(); state.user = null; render() } }
    else if (action === 'checklist-dismiss') { storage.set('hc.checklistDismissed', '1'); render() }
    else if (action === 'install-pwa' && state.installPrompt) { await state.installPrompt.prompt(); state.installPrompt = null; render() }
  } catch (error) { toast(error instanceof Error ? error.message : 'Action failed', 'error') }
})

ROOT.addEventListener('change', async event => {
  const action = event.target.dataset.action
  try {
    if (event.target.name === 'file' && event.target.form?.id === 'file-upload-form') await uploadFile(event.target.form)
    else if (action === 'profile-change') await changeProfile(event.target.value)
    else if (action === 'model-change') { state.selectedModel = event.target.value; storage.set('model', state.selectedModel) }
    else if (action === 'theme-change') {
      const value = event.target.value
      if (value) storage.set('hc.theme', value)
      else storage.remove('hc.theme')
      applyTheme()
    }
  } catch (error) { toast(error instanceof Error ? error.message : 'Change failed', 'error') }
})

ROOT.addEventListener('input', event => {
  if (event.target.id === 'session-search') {
    state.sessionQuery = event.target.value
    const wrap = event.target.closest('.page')
    const position = event.target.selectionStart
    ROOT.innerHTML = shell(renderSessions())
    const input = document.getElementById('session-search')
    if (input) { input.focus(); input.setSelectionRange(position, position) }
  }
  const textarea = event.target.closest('#composer-form textarea, #gateway-composer textarea')
  if (textarea) {
    if (event.target.closest('#composer-form')) state.composerDraft = textarea.value
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`
  }
})

ROOT.addEventListener('keydown', event => {
  const textarea = event.target.closest('#composer-form textarea, #gateway-composer textarea')
  if (!textarea || event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  textarea.form.requestSubmit()
})

ROOT.addEventListener('submit', async event => {
  event.preventDefault()
  try {
    if (event.target.id === 'login-form') await login(event.target)
    else if (event.target.id === 'session-create-form') {
      const title = String(new FormData(event.target).get('title') || '').trim(); await createSession(title)
    } else if (event.target.id === 'composer-form') {
      const textarea = event.target.querySelector('textarea'); const text = textarea.value; textarea.value = ''; state.composerDraft = ''; await startRun(text)
    } else if (event.target.id === 'job-create-form') await createJob(event.target)
    else if (event.target.id === 'file-upload-form') await uploadFile(event.target)
    else if (event.target.id === 'prompt-create-form') await createPrompt(event.target)
    else if (event.target.id === 'admin-user-form') await createAdminUser(event.target)
    else if (event.target.id === 'password-change-form') await changePassword(event.target)
    else if (event.target.id === 'gateway-composer') {
      const textarea = event.target.querySelector('textarea'); const text = textarea.value; textarea.value = ''; await gatewaySubmit(text)
    } else if (event.target.dataset.gatewayClarify) {
      const data = new FormData(event.target); gatewayAnswer(event.target.dataset.gatewayClarify, { answer: String(data.get('answer') || '') })
    } else if (event.target.id === 'settings-bridge-form') {
      const url = String(new FormData(event.target).get('bridge') || '').trim().replace(/\/+$/,'')
      if (url && !/^https?:\/\//i.test(url)) throw new Error('Bridge URL must start with http:// or https://')
      storage.set('bridgeUrl', url); storage.clearAuth(); state.user = null; toast('Bridge saved. Sign in to that bridge.', 'success'); render()
    }
  } catch (error) { toast(error instanceof Error ? error.message : 'Operation failed', 'error') }
})

window.addEventListener('popstate', async () => { state.route = normaliseRoute(location.pathname); await loadRoute() })
window.addEventListener('beforeinstallprompt', event => { event.preventDefault(); state.installPrompt = event; if (state.route === '/settings') render() })
window.addEventListener('online', () => { syncOffline(); toast('Back online', 'success') })
window.addEventListener('offline', () => { syncOffline() })

async function boot() {
  renderBoot()
  try {
    if (!storage.get('access')) {
      if (!storage.get('refresh') || !(await refreshAccess())) { state.user = null; return }
    }
    state.user = await apiFetch('/api/auth/me')
    storage.setJson('user', state.user)
    await loadProfiles()
    await resolveHandoff()
    await loadRoute()
  } catch {
    storage.clearAuth(); state.user = null
  } finally { state.booting = false; render() }

  if ('serviceWorker' in navigator && location.protocol.startsWith('http')) {
    navigator.serviceWorker.register('/sw.js').then(registration => {
      registration.addEventListener('updatefound', () => {
        const worker = registration.installing
        worker?.addEventListener('statechange', () => {
          if (worker.state === 'installed' && navigator.serviceWorker.controller) {
            toast('A new version is ready — tap here to reload.', 'info', 15000)
            document.querySelector('#toast-stack .toast-static:last-child')?.addEventListener('click', () => location.reload())
          }
        })
      })
    }).catch(() => undefined)
  }
}

void boot()
