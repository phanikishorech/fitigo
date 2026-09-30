import { useEffect, useRef, type ReactNode } from 'react'
import Icon, { type IconName } from '../components/common/Icon'
import { Link } from './UI'
import { useOwner } from './context'
import { navigate } from '../router'

export function GymSelector() {
  const { gyms, gymId, selectGym, roles } = useOwner()
  return <div className="ow-gym-selector"><Icon name="gym" /><label><span>YOUR WORKSPACE</span><select aria-label="Selected gym" value={gymId || ''} onChange={e => e.target.value === 'new' ? navigate('/owner/gyms/create') : selectGym(Number(e.target.value))}>{!gymId && <option value="">Select a gym</option>}{gyms.map(g => <option key={g.id} value={g.id}>{g.name}{g.city ? ` · ${g.city}` : ''}</option>)}{roles.includes('GYM_OWNER') && <option value="new">+ Add new gym</option>}</select></label></div>
}
export function ownerLinks(gymId?: number): { label: string; icon: IconName; to: string }[] {
  return [
    { label: 'Dashboard', icon: 'home', to: '/owner/dashboard' }, { label: 'My gyms', icon: 'gym', to: '/owner/gyms' },
    { label: 'Bookings', icon: 'calendar', to: '/owner/bookings' }, { label: 'Members', icon: 'user', to: '/owner/members' },
    { label: 'Classes & slots', icon: 'clock', to: gymId ? `/owner/gyms/${gymId}/classes` : '/owner/gyms' },
    { label: 'Membership plans', icon: 'ticket', to: gymId ? `/owner/gyms/${gymId}/memberships` : '/owner/gyms' },
    { label: 'Staff', icon: 'shield', to: '/owner/staff' }, { label: 'Check-in', icon: 'qr', to: '/owner/check-in' },
    { label: 'Revenue', icon: 'wallet', to: '/owner/revenue' }, { label: 'Analytics', icon: 'chart', to: '/owner/analytics' },
    { label: 'Settings', icon: 'settings', to: '/owner/settings' }
  ]
}
export default function OwnerLayout({ children, path }: { children: ReactNode; path: string }) {
  const { user, gymId, roles } = useOwner()
  const main = useRef<HTMLElement>(null)
  const owner = roles.includes('GYM_OWNER')
  const links = ownerLinks(gymId).filter(l => owner || ['Check-in', 'Settings'].includes(l.label))
  const active = (to: string) => path === to || (to !== '/owner/gyms' && path.startsWith(`${to}/`)) || (to === '/owner/dashboard' && path === '/owner')
  useEffect(() => { window.scrollTo(0, 0); main.current?.focus(); document.title = `${links.find(l => active(l.to))?.label || 'Owner portal'} · FitiGo` }, [path])
  return <div className="ow-layout"><a className="fg-skip" href="#owner-main">Skip to content</a><aside className="ow-sidebar"><Link className="fg-logo ow-logo" to={owner ? '/owner/dashboard' : '/owner/check-in'}><span className="fg-logo-mark"><Icon name="gym" /></span>Fiti<span>Go</span><small>OWNER</small></Link><span className="ow-nav-label">WORKSPACE</span><nav aria-label="Owner navigation">{links.map(l => <a key={l.label} href={l.to} aria-current={active(l.to) ? 'page' : undefined} className={`ow-nav-link ${active(l.to) ? 'is-active' : ''}`} onClick={e => { if (!e.ctrlKey && !e.metaKey && !e.shiftKey && e.button === 0) { e.preventDefault(); navigate(l.to) } }}><Icon name={l.icon} /><span>{l.label}</span>{l.label === 'Check-in' && <span className="ow-nav-shortcut"><Icon name="qr" size={14} /></span>}</a>)}</nav><div className="ow-sidebar-bottom"><Link className="ow-nav-link" to="/owner/help"><Icon name="help" />Help & support</Link><Link className="ow-profile" to="/owner/settings"><span className="ow-avatar">{user.first_name?.[0] || <Icon name="user" />}</span><span><strong>{user.first_name || 'Account'} {user.last_name}</strong><small>{owner ? 'Gym owner' : 'Check-in staff'}</small></span><Icon name="down" size={16} /></Link></div></aside>
    <div className="ow-workspace"><header className="ow-topbar"><div className="ow-mobile-brand"><Link className="fg-logo" to="/owner/dashboard">Fiti<span>Go</span></Link><small>Owner</small></div><form className="ow-header-search" onSubmit={e => { e.preventDefault(); const id = String(new FormData(e.currentTarget).get('booking')).trim(); if (/^[1-9]\d*$/.test(id)) navigate(`/owner/bookings/${id}`) }}><Icon name="search" /><input name="booking" type="text" pattern="[1-9][0-9]*" inputMode="numeric" required aria-label="Find booking by ID" placeholder="Find booking by ID…" /><button type="submit" aria-label="Find booking"><Icon name="arrow" size={16} /></button></form><div className="ow-header-right"><span className="ow-desktop-selector"><GymSelector /></span><Link className="ow-icon-button" to="/owner/notifications" label="Notifications"><Icon name="bell" /></Link><Link className="ow-avatar" to="/owner/settings" label="Owner profile">{user.first_name?.[0] || <Icon name="user" />}</Link></div></header><div className="ow-mobile-selector"><GymSelector /></div><main id="owner-main" ref={main} tabIndex={-1} className="ow-main">{children}</main><footer className="ow-footer"><span>FitiGo Owner</span><span>Built for your everyday operations.</span><Link to="/owner/help">Help & support</Link></footer></div>
    <nav className="ow-mobile-nav" aria-label="Mobile navigation">{(owner ? [{ label: 'Home', icon: 'home', to: '/owner/dashboard' }, { label: 'Gyms', icon: 'gym', to: '/owner/gyms' }, { label: 'Bookings', icon: 'calendar', to: '/owner/bookings' }, { label: 'Check-in', icon: 'qr', to: '/owner/check-in' }, { label: 'More', icon: 'menu', to: '/owner/more' }] : [{ label: 'Check-in', icon: 'qr', to: '/owner/check-in' }, { label: 'Account', icon: 'user', to: '/owner/settings' }]).map(l => <Link key={l.to} to={l.to} className={active(l.to) ? 'is-active' : ''}><Icon name={l.icon as IconName} /><span>{l.label}</span></Link>)}</nav>
  </div>
}