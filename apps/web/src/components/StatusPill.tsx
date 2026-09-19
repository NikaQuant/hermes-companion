import type { ReactNode } from 'react'

export function StatusPill({ status, children }: { status: 'online' | 'offline' | 'warn' | 'neutral'; children: ReactNode }) {
  return <span className={`status-pill status-${status}`}><span className="status-dot" />{children}</span>
}
