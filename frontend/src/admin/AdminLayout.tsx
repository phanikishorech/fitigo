import { useEffect, useState, type ReactNode } from 'react'
import type { User } from '../services/accountService'
import { navigate } from '../router'
import { adminAuthService } from './services'
import { Avatar, Button, Icon, Link, Modal, SearchInput, personName, readable, useToast } from './UI'
import { useMutation } from '../hooks/useResource'
import type { IconName } from '../components/common/Icon'

const navigation: { label: string; path: string; icon: IconName }[] = [
  { label: 'Dashboard', path: '/admin/dashboard', icon: 'home' },
  { label: 'Users', path: '/admin/users', icon: 'user' },
  { label: 'Gyms', path: '/admin/gyms', icon: 'gym' },
  { label: 'Bookings', path: '/admin/bookings', icon: 'ticket' },
  { label: 'Reports', path: '/admin/reports', icon: 'chart' }
]
export function Logo() { return <Link to="/admin/dashboard" className="ad-logo"><span className="fg-logo-mark"><Icon name="gym" size={23} /></span><span>Fiti<span>Go</span></span><small>ADMIN</small></Link> }
export function AdminSidebar({ path, logout }: { path: string; logout: () => void }) {
  return <><Logo /><div className="ad-nav-caption">WORKSPACE</div><nav aria-label="Admin navigation">{navigation.map(item => <a key={item.path} href={item.path} aria-current={path === item.path || path.startsWith(item.path + '/') || (path === '/admin' && item.label === 'Dashboard') ? 'page' : undefined} onClick={e => { if (!e.ctrlKey && !e.metaKey && !e.shiftKey) { e.preventDefault(); navigate(item.path) } }}><Icon name={item.icon} />{item.label}</a>)}<span className="ad-nav-unavailable" title="Audit logs are not available in the current API"><Icon name="shield" />Audit Logs<small>Planned</small></span></nav><div className="ad-sidebar-bottom"><nav aria-label="Account navigation"><Link to="/admin/profile"><Icon name="user" />Admin Profile</Link><button onClick={logout}><Icon name="logout" />Logout</button></nav><div className="ad-workspace-note"><Icon name="shield" /><span>FitiGo Administration<small>Platform management workspace</small></span></div></div></>
}
export function AdminHeader({ user, roles, onMenu }: { user: User; roles: string[]; onMenu: () => void }) {
  const [search, setSearch] = useState(''); const [scope, setScope] = useState('users')
  return <header className="ad-header"><Button className="ad-menu-button" variant="text" aria-label="Open navigation" onClick={onMenu}><Icon name="menu" /></Button><span className="ad-mobile-brand">FitiGo <small>Admin</small></span><form className="ad-global-search" onSubmit={e => { e.preventDefault(); navigate(`/admin/${scope}?q=${encodeURIComponent(search.trim())}`) }}><SearchInput value={search} onChange={setSearch} placeholder="Search the platform…" /><select aria-label="Search category" value={scope} onChange={e => setScope(e.target.value)}><option value="users">Users</option><option value="gyms">Gyms</option><option value="bookings">Bookings</option></select><Button type="submit" variant="text" aria-label="Search selected category"><Icon name="arrow" size={17} /></Button></form><div className="ad-header-account"><Link to="/admin/notifications" className="ad-header-bell" label="Notifications"><Icon name="bell" /></Link><Link to="/admin/profile" className="ad-profile-link"><Avatar name={personName(user)} /><span><strong>{personName(user)}</strong><small>{readable(roles.includes('SUPER_ADMIN') ? 'SUPER_ADMIN' : 'ADMIN')}</small></span><Icon name="down" size={15} /></Link></div></header>
}
export default function AdminLayout({ children, path, user, roles }: { children: ReactNode; path: string; user: User; roles: string[] }) {
  const [menu, setMenu] = useState(false); const [logout, setLogout] = useState(false); const mutation = useMutation(); const toast = useToast()
  useEffect(() => { setMenu(false); document.getElementById('admin-main')?.focus(); window.scrollTo(0, 0) }, [path])
  useEffect(() => { document.title = `${navigation.find(item => path.startsWith(item.path))?.label || 'Admin'} · FitiGo` }, [path])
  return <><a className="fg-skip" href="#admin-main">Skip to main content</a><aside className="ad-sidebar"><AdminSidebar path={path} logout={() => setLogout(true)} /></aside><div className="ad-workspace"><AdminHeader user={user} roles={roles} onMenu={() => setMenu(true)} /><main id="admin-main" className="ad-main" tabIndex={-1}>{children}<footer className="ad-footer"><span>FitiGo Admin Portal</span><span>Platform control. Thoughtfully simple.</span></footer></main></div>{menu && <div className="ad-navigation-drawer"><Modal title="FitiGo Admin" onClose={() => setMenu(false)}><AdminSidebar path={path} logout={() => { setMenu(false); setLogout(true) }} /></Modal></div>}{logout && <Modal title="Sign out of FitiGo?" onClose={() => { if (!mutation.pending) setLogout(false) }}><p>You’ll need to sign in again to access the admin workspace.</p><div className="ad-dialog-actions"><Button variant="secondary" disabled={mutation.pending} onClick={() => setLogout(false)}>Stay signed in</Button><Button variant="danger" loading={mutation.pending} onClick={() => void mutation.run(async () => { try { await adminAuthService.logout() } catch { toast('Signed out locally. Server session revocation could not be confirmed.', 'warning') } navigate('/admin/login') })}>Sign out</Button></div></Modal>}</>
}