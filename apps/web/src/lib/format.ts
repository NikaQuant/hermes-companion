import type { HermesMessage, HermesSession } from '../types'

export function sessionId(session: HermesSession): string {
  return String(session.id || session.session_id || '')
}

export function sessionTitle(session: HermesSession): string {
  return String(session.title || session.name || session.preview || 'Untitled session')
}

export function messageText(message: HermesMessage): string {
  if (typeof message.content === 'string') return message.content
  if (typeof message.text === 'string') return message.text
  if (Array.isArray(message.content)) {
    return message.content.map(part => {
      if (typeof part === 'string') return part
      if (part && typeof part === 'object') {
        const record = part as Record<string, unknown>
        return String(record.text || record.content || '')
      }
      return ''
    }).filter(Boolean).join('\n')
  }
  if (message.content && typeof message.content === 'object') {
    const content = message.content as Record<string, unknown>
    return String(content.text || content.content || JSON.stringify(content, null, 2))
  }
  return ''
}

export function listFromPayload<T>(payload: unknown, candidates: string[]): T[] {
  if (Array.isArray(payload)) return payload as T[]
  if (payload && typeof payload === 'object') {
    const source = payload as Record<string, unknown>
    for (const key of candidates) {
      if (Array.isArray(source[key])) return source[key] as T[]
    }
  }
  return []
}

export function timestamp(value: unknown): string {
  if (!value) return ''
  const numeric = typeof value === 'number' && value < 10_000_000_000 ? value * 1000 : value
  const date = new Date(numeric as string | number)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  }).format(date)
}

export function truncate(value: string, length = 120): string {
  return value.length <= length ? value : `${value.slice(0, length - 1)}…`
}
