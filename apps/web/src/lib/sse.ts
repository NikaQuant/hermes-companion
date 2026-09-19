import { absoluteApiUrl, refreshAccess } from './api'
import { storage } from './storage'

export interface SseMessage {
  type: string
  data: unknown
  id?: string
}

function parseBlock(block: string): SseMessage | null {
  let type = 'message'
  let id: string | undefined
  const data: string[] = []
  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue
    const colon = line.indexOf(':')
    const field = colon >= 0 ? line.slice(0, colon) : line
    const value = colon >= 0 ? line.slice(colon + 1).replace(/^ /, '') : ''
    if (field === 'event') type = value
    if (field === 'id') id = value
    if (field === 'data') data.push(value)
  }
  if (!data.length && type === 'message') return null
  const raw = data.join('\n')
  let parsed: unknown = raw
  if (raw) {
    try { parsed = JSON.parse(raw) } catch { parsed = raw }
  }
  if (parsed && typeof parsed === 'object' && 'event' in parsed && type === 'message') {
    type = String((parsed as Record<string, unknown>).event)
  }
  return { type, data: parsed, id }
}

async function connect(
  path: string,
  onMessage: (message: SseMessage) => void,
  signal: AbortSignal,
  lastEventId?: string
): Promise<Response> {
  const headers: Record<string, string> = {
    Accept: 'text/event-stream',
    Authorization: `Bearer ${storage.get('access')}`
  }
  if (lastEventId) headers['Last-Event-ID'] = lastEventId
  return fetch(absoluteApiUrl(path), { headers, signal })
}

export async function streamSse(
  path: string,
  onMessage: (message: SseMessage) => void,
  signal: AbortSignal,
  lastEventId?: string
): Promise<void> {
  let response = await connect(path, onMessage, signal, lastEventId)
  if (response.status === 401 && await refreshAccess()) {
    response = await connect(path, onMessage, signal, lastEventId)
  }
  if (!response.ok || !response.body) throw new Error(`Stream failed (${response.status})`)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() || ''
    for (const block of blocks) {
      const message = parseBlock(block)
      if (message) onMessage(message)
    }
  }
  if (buffer.trim()) {
    const message = parseBlock(buffer)
    if (message) onMessage(message)
  }
}
