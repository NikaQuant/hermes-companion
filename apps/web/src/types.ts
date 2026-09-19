export interface User {
  id: string
  email: string
  role: string
}

export interface ProfilePermissions {
  read: boolean
  chat: boolean
  session_write: boolean
  run_control: boolean
  approval: boolean
  jobs_write: boolean
}

export interface HermesProfile {
  slug: string
  label: string
  description: string
  accent: string
  configured: boolean
  permissions: ProfilePermissions
}

export interface HermesSession {
  id?: string
  session_id?: string
  title?: string
  name?: string
  preview?: string
  last_active?: number | string
  updated_at?: number | string
  created_at?: number | string
  [key: string]: unknown
}

export interface HermesMessage {
  id?: string | number
  role?: string
  content?: unknown
  text?: string
  created_at?: number | string
  display_kind?: string
  tool_calls?: unknown
  [key: string]: unknown
}

export interface ToolEvent {
  id: string
  event: string
  tool?: string
  preview?: string
  error?: boolean
  duration?: number
  timestamp?: number
  status?: string
  [key: string]: unknown
}

export interface RunStatus {
  run_id: string
  status: string
  output?: string
  pending_steer?: string
  approval?: Record<string, unknown>
  session_id?: string
  error?: unknown
  [key: string]: unknown
}

export interface Job {
  id?: string
  job_id?: string
  name?: string
  prompt?: string
  schedule?: string
  enabled?: boolean
  paused?: boolean
  next_run_at?: string | number
  last_run_at?: string | number
  [key: string]: unknown
}

export interface Tokens {
  access_token: string
  refresh_token: string
  access_expires_at: number
  refresh_expires_at: number
  user: User
}
