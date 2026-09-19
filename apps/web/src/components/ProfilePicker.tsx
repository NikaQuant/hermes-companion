import { Bot, ChevronDown, ShieldAlert } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useAuth } from '../context/AuthContext'

export function ProfilePicker({ compact = false }: { compact?: boolean }) {
  const { profiles, activeProfile, setActiveProfile } = useAuth()
  const configured = profiles.filter(profile => profile.configured)
  const current = profiles.find(profile => profile.slug === activeProfile)

  return (
    <label className={`profile-picker ${compact ? 'compact' : ''}`}>
      <span className="profile-picker-icon" style={{ '--profile-accent': current?.accent || '#8b5cf6' } as CSSProperties}>
        <Bot size={17} />
      </span>
      <span className="profile-picker-copy">
        {!compact ? <small>Active agent</small> : null}
        <strong>{current?.label || 'Select profile'}</strong>
      </span>
      <select value={activeProfile} onChange={event => setActiveProfile(event.target.value)}>
        {configured.map(profile => <option key={profile.slug} value={profile.slug}>{profile.label}</option>)}
      </select>
      <ChevronDown size={15} className="profile-picker-chevron" />
      {!configured.length ? <ShieldAlert size={16} /> : null}
    </label>
  )
}
