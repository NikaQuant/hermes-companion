/**
 * Hermes Companion — thin Desktop handoff surface.
 *
 * It never contains Hermes API keys. It reads the focused regular-Hermes
 * profile/session IDs from Desktop state and opens the authenticated Companion.
 */
import {
  Button,
  Codicon,
  Input,
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  STATUSBAR_AREAS,
  host,
  useValue
} from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'hermes-companion'
const ROUTE = '/hermes-companion'
const DEFAULT_URL = 'http://127.0.0.1:8787'
let pluginCtx = null
let storedUrl = DEFAULT_URL

function cleanUrl(value) {
  const trimmed = String(value || '').trim().replace(/\/+$/, '')
  if (!trimmed) return DEFAULT_URL
  try {
    const parsed = new URL(trimmed)
    if (!['http:', 'https:'].includes(parsed.protocol)) return DEFAULT_URL
    return parsed.toString().replace(/\/$/, '')
  } catch {
    return DEFAULT_URL
  }
}

function companionUrl(profile, sessionId) {
  const url = new URL(storedUrl || DEFAULT_URL)
  if (profile) url.searchParams.set('profile', profile)
  if (sessionId) url.searchParams.set('session', sessionId)
  return url.toString()
}

function openExternal(url) {
  // The Desktop renderer denies window.open by security policy (GHSA-9f4c-93c8-jc8g —
  // "always deny, trusted links arrive via hermes:openExternal"). The audited channel is
  // the preload bridge; keep window.open only as a fallback for non-Desktop hosts.
  if (window.hermesDesktop?.openExternal) {
    void window.hermesDesktop.openExternal(url)
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}

function ContextSummary() {
  const profile = useValue(host.state.focusedSessionProfile)
  const durableId = useValue(host.state.focusedStoredSessionId)
  const runtimeId = useValue(host.state.focusedSessionId)
  const sessionId = durableId || runtimeId || ''

  return jsxs('div', {
    style: { display: 'grid', gridTemplateColumns: '140px minmax(0,1fr)', gap: 8, fontSize: 12 },
    children: [
      jsx('span', { style: { color: 'var(--ui-text-tertiary)' }, children: 'Profile' }),
      jsx('code', { children: profile || 'No focused profile' }),
      jsx('span', { style: { color: 'var(--ui-text-tertiary)' }, children: 'Stored session' }),
      jsx('code', { style: { overflowWrap: 'anywhere' }, children: sessionId || 'No stored session is focused' })
    ]
  })
}

function CompanionPage() {
  const profile = useValue(host.state.focusedSessionProfile)
  const durableId = useValue(host.state.focusedStoredSessionId)
  const runtimeId = useValue(host.state.focusedSessionId)
  const sessionId = durableId || runtimeId || ''
  const [url, setUrl] = useState(storedUrl)
  const [revision, setRevision] = useState(0)
  const handoff = useMemo(
    () => companionUrl(profile, sessionId),
    [profile, sessionId, revision]
  )

  useEffect(() => {
    let cancelled = false
    Promise.resolve(pluginCtx?.storage?.get?.('bridgeUrl'))
      .then(value => {
        if (cancelled || !value) return
        storedUrl = cleanUrl(value)
        setUrl(storedUrl)
      })
      .catch(() => undefined)
    return () => { cancelled = true }
  }, [])

  async function save() {
    storedUrl = cleanUrl(url)
    setUrl(storedUrl)
    await pluginCtx?.storage?.set?.('bridgeUrl', storedUrl)
    setRevision(value => value + 1)
    host.notify({ kind: 'success', message: 'Hermes Companion address saved.' })
  }

  async function copyHandoff() {
    await navigator.clipboard.writeText(handoff)
    host.notify({ kind: 'success', message: 'Companion handoff link copied.' })
  }

  return jsxs('div', {
    style: { maxWidth: 860, margin: '0 auto', padding: 28, display: 'grid', gap: 18 },
    children: [
      jsxs('header', {
        children: [
          jsx('div', {
            style: { color: 'var(--ui-text-tertiary)', fontSize: 11, letterSpacing: '.12em' },
            children: 'HERMES COMPANION'
          }),
          jsx('h1', { style: { margin: '8px 0 6px' }, children: 'Continue this Desktop experience anywhere' }),
          jsx('p', {
            style: { color: 'var(--ui-text-tertiary)', maxWidth: 700 },
            children: 'Open the authenticated Companion with the focused regular-Hermes profile and durable session. No Hermes API key is stored in this plugin.'
          })
        ]
      }),
      jsxs('section', {
        style: {
          border: '1px solid var(--ui-stroke-secondary)', borderRadius: 12,
          padding: 18, display: 'grid', gap: 12
        },
        children: [
          jsx('strong', { children: 'Current Desktop context' }),
          jsx(ContextSummary, {}),
          jsxs('div', {
            style: { display: 'flex', gap: 8, flexWrap: 'wrap' },
            children: [
              jsx(Button, {
                variant: 'primary', disabled: !sessionId,
                onClick: () => openExternal(handoff), children: 'Continue on web or phone'
              }),
              jsx(Button, { onClick: () => openExternal(storedUrl), children: 'Open Command Center' }),
              jsx(Button, { disabled: !sessionId, onClick: copyHandoff, children: 'Copy handoff link' })
            ]
          })
        ]
      }),
      jsxs('section', {
        style: {
          border: '1px solid var(--ui-stroke-secondary)', borderRadius: 12,
          padding: 18, display: 'grid', gap: 10
        },
        children: [
          jsx('strong', { children: 'Companion address' }),
          jsx(Input, {
            value: url,
            onChange: event => setUrl(event.target.value),
            placeholder: DEFAULT_URL
          }),
          jsx('small', {
            style: { color: 'var(--ui-text-tertiary)' },
            children: 'Use the local bridge URL on this machine, or your private HTTPS URL for remote/mobile handoff.'
          }),
          jsx('div', { children: jsx(Button, { onClick: save, children: 'Save address' }) })
        ]
      }),
      jsx('section', {
        style: {
          border: '1px solid rgba(244,63,94,.25)', borderRadius: 12,
          padding: 16, color: 'var(--ui-text-tertiary)', fontSize: 12
        },
        children: 'Safety World is intentionally outside this plugin. Install it only in the regular Hermes Desktop home, never under HermesSafety or a Hermes-Safety data tree.'
      })
    ]
  })
}

function StatusButton() {
  const profile = useValue(host.state.focusedSessionProfile)
  const sessionId = useValue(host.state.focusedStoredSessionId)
  return jsxs('button', {
    type: 'button',
    title: sessionId ? `Open Companion · ${profile || 'default'}` : 'Open Hermes Companion',
    onClick: () => host.navigate(ROUTE),
    style: {
      border: 0, background: 'transparent', color: 'inherit', cursor: 'pointer',
      display: 'flex', alignItems: 'center', gap: 5, height: '100%', padding: '0 6px'
    },
    children: [jsx(Codicon, { name: 'device-mobile' }), jsx('span', { children: 'Companion' })]
  })
}

export default {
  id: ID,
  name: 'Hermes Companion',
  description: 'Continue the focused regular-Hermes session in the private web, PWA, Android, or Windows companion.',
  defaultEnabled: false,
  register(ctx) {
    pluginCtx = ctx

    try {
      Promise.resolve(ctx.storage?.get?.('bridgeUrl'))
        .then(value => { if (value) storedUrl = cleanUrl(value) })
        .catch(() => undefined)
    } catch {
      storedUrl = DEFAULT_URL
    }

    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: ROUTE },
        render: () => jsx(CompanionPage, {})
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        order: 62,
        data: { codicon: 'device-mobile', label: 'Companion', path: ROUTE }
      },
      {
        id: 'status',
        area: STATUSBAR_AREAS.right,
        order: 55,
        render: () => jsx(StatusButton, {})
      },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: {
          id: `${ID}.open`,
          label: 'Hermes Companion: Open panel',
          keywords: ['companion', 'mobile', 'phone', 'handoff'],
          run: () => host.navigate(ROUTE)
        }
      },
      {
        id: 'external',
        area: PALETTE_AREA,
        data: {
          id: `${ID}.external`,
          label: 'Hermes Companion: Open external app',
          keywords: ['companion', 'browser', 'pwa'],
          run: () => openExternal(storedUrl)
        }
      }
    ])

    ctx.onDispose?.(() => { pluginCtx = null })
  }
}
