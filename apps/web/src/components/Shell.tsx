import {
  Activity, Bot, CalendarClock, ChevronLeft, ChevronRight, ClipboardList, LogOut,
  Menu, MessageSquareText, Settings, ShieldCheck, X
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ProfilePicker } from './ProfilePicker'

const nav = [
  { to: '/', label: 'Command Center', icon: Activity, end: true },
  { to: '/chat', label: 'Chat', icon: MessageSquareText },
  { to: '/sessions', label: 'Sessions', icon: ClipboardList },
  { to: '/automations', label: 'Automations', icon: CalendarClock },
  { to: '/audit', label: 'Audit', icon: ShieldCheck },
  { to: '/settings', label: 'Settings', icon: Settings }
]

export function Shell() {
  const { user, logout } = useAuth()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('hermes.companion.navCollapsed') === '1')

  useEffect(() => setMobileOpen(false), [location.pathname])
  const toggleCollapsed = () => {
    const next = !collapsed
    setCollapsed(next)
    localStorage.setItem('hermes.companion.navCollapsed', next ? '1' : '0')
  }

  return (
    <div className={`app-shell ${collapsed ? 'nav-collapsed' : ''}`}>
      <header className="mobile-header">
        <button className="icon-button" onClick={() => setMobileOpen(true)} aria-label="Open menu"><Menu /></button>
        <div className="brand compact"><span className="brand-mark">H</span><strong>Hermes</strong></div>
        <ProfilePicker compact />
      </header>
      {mobileOpen ? <button className="mobile-scrim" onClick={() => setMobileOpen(false)} aria-label="Close menu" /> : null}
      <aside className={`sidebar ${mobileOpen ? 'mobile-open' : ''}`}>
        <div className="sidebar-top">
          <div className="brand">
            <span className="brand-mark">H</span>
            <span className="brand-copy"><strong>Hermes</strong><small>Companion</small></span>
          </div>
          <button className="icon-button mobile-only" onClick={() => setMobileOpen(false)}><X size={19} /></button>
        </div>
        <div className="desktop-profile"><ProfilePicker /></div>
        <nav className="sidebar-nav">
          {nav.map(item => {
            const Icon = item.icon
            return (
              <NavLink key={item.to} to={item.to} end={item.end} title={collapsed ? item.label : undefined}>
                <Icon size={18} /><span>{item.label}</span>
              </NavLink>
            )
          })}
        </nav>
        <div className="sidebar-footer">
          <div className="user-chip">
            <span><Bot size={16} /></span>
            <div><strong>{user?.email?.split('@')[0] || 'Operator'}</strong><small>{user?.role || 'admin'}</small></div>
          </div>
          <button className="sidebar-logout" onClick={() => void logout()} title="Sign out"><LogOut size={17} /><span>Sign out</span></button>
          <button className="collapse-button desktop-only" onClick={toggleCollapsed} title={collapsed ? 'Expand navigation' : 'Collapse navigation'}>
            {collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}<span>Collapse</span>
          </button>
        </div>
      </aside>
      <main className="main-content"><Outlet /></main>
    </div>
  )
}
