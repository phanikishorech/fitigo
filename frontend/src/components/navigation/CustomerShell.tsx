import { useEffect, useState, type ReactNode } from 'react'
import { getAccessToken, subscribeAuth } from '../../auth'
import { openAuthModal } from '../../authUi'
import { getStoredLocation } from '../../screens/NearbyGyms/LocationStore'
import Icon, { type IconName } from '../common/Icon'
import { Button, Link } from '../common/UI'
import '../../customer.css'

const desktop: { label: string; to: string; icon: IconName }[] = [
  { label: 'Home', to: '/home', icon: 'home' }, { label: 'Explore', to: '/explore', icon: 'search' },
  { label: 'Bookings', to: '/bookings', icon: 'calendar' }, { label: 'Memberships', to: '/membership', icon: 'ticket' },
  { label: 'Wallet', to: '/wallet', icon: 'wallet' }
]
const mobile: typeof desktop = [desktop[0], desktop[1], desktop[3], { label: 'Profile', to: '/profile', icon: 'user' }]
export default function CustomerShell({ children, path }: { children: ReactNode; path: string }) {
  const [authed, setAuthed] = useState(!!getAccessToken())
  useEffect(() => subscribeAuth(() => setAuthed(!!getAccessToken())), [])
  useEffect(() => { window.scrollTo(0, 0); document.title = 'FitiGo — Your Fitness. Your Way.'; document.getElementById('customer-content')?.focus({ preventScroll: true }) }, [path])
  const location = getStoredLocation()
  const active = (to: string) => path === to || (to === '/home' && path === '/') || (to === '/explore' && /explore|nearby|gyms/.test(path)) || (to === '/membership' && (/^\/membership(\/|$)/.test(path) || ['/profile/membership', '/profile/access', '/profile/access/today', '/access/qr', '/my-access'].includes(path)))
  return <div className="fg-app"><a className="fg-skip" href="#customer-content">Skip to content</a>
    <header className="fg-header"><div className="fg-header-inner">
      <Link to="/home" className="fg-logo" label="FitiGo home"><span className="fg-logo-mark"><Icon name="gym" size={23} /></span>Fiti<span>Go</span></Link>
      <Link to="/location" className="fg-location"><Icon name="pin" /><span><small>YOUR LOCATION</small><strong>{location?.location_name ?? 'Choose location'}</strong></span><Icon name="down" size={15} /></Link>
      <nav className="fg-desktop-nav" aria-label="Main navigation">{desktop.map(item => <Link key={item.to} to={item.to} className={active(item.to) ? 'is-active' : ''}>{item.label}</Link>)}</nav>
      <div className="fg-header-actions"><Link to="/cart" className="fg-icon-button" label="Your cart"><Icon name="bag" /></Link>{authed ? <><Link to="/access/qr" className="fg-qr-link"><Icon name="qr" />My access</Link><Link to="/profile" className="fg-avatar" label="Your profile"><Icon name="user" /></Link></> : <Button variant="secondary" onClick={() => openAuthModal(path)}>Sign in</Button>}</div>
    </div></header>
    <main id="customer-content" className="fg-main" tabIndex={-1}>{children}</main>
    <footer className="fg-footer"><Link to="/home" className="fg-logo">Fiti<span>Go</span></Link><p>Your Fitness. Your Way.</p><span>Discover. Book. Show up.</span></footer>
    <nav className="fg-bottom-nav" aria-label="Mobile navigation">{mobile.map(item => <Link key={item.to} to={item.to} className={active(item.to) ? 'is-active' : ''}><Icon name={item.icon} /><span>{item.label}</span></Link>)}</nav>
  </div>
}