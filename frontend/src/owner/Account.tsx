import NotificationCenter from '../components/common/NotificationCenter'
import SupportContact from '../components/common/SupportContact'
import { istDateTime } from '../utils/membership'
import { useState } from 'react'
import { useOwner } from './context'
import { ownerService } from './services'
import { useMutation, useResource } from '../hooks/useResource'
import { Button, Card, ConfirmDialog, EmptyState, ErrorState, Link, Notice, PageHeader, Pagination, Skeleton, StatusBadge, Unavailable } from './UI'
import { logoutSession } from '../session/store'
import { navigate } from '../router'
import Icon from '../components/common/Icon'
import { ownerLinks } from './OwnerLayout'
import ChangePassword from './ChangePassword'
import AccountProfileEditor from '../components/common/AccountProfileEditor'
import Members from './Members'

export default function Account({ page }: { page: string }) {
  if (page === 'notifications') return <NotificationCenter />
  if (page === 'settings') return <Settings />
  if (page === 'more') return <More />
  if (page.startsWith('members')) return <Members />
  if (page === 'help') return <div className="ow-stack"><PageHeader title="Help & support" description="A few things to know about your workspace." /><Card title="Managing your gym"><div className="ow-help"><h3>How do I get my gym live?</h3><p>Create a gym, complete the setup steps and submit the draft for approval. The review status appears in My gyms. No approval timeline is provided.</p><h3>Who can scan QR codes?</h3><p>Gym owners may scan for their own gyms; assigned staff may scan for assigned gyms. The server validates gym scope, membership or booking eligibility, visit timing and duplicate entry. Use My Access for personal membership entry and the booking pass for named booking visitors.</p><h3>Why are some features unavailable?</h3><p>This portal only displays data provided by the existing APIs. The member directory shows gym-scoped operational history; account editing and reports use authenticated APIs. Notification preferences and read state are shown when enabled in this deployment; email acceptance is not inbox delivery. Photo deletion availability and pending cleanup are shown on the gym Photos page. Gateway rescheduling and in-app refund initiation need additional policy and backend support. Cancellation does not automatically refund a payment.</p><h3>Need help with your account?</h3><SupportContact /></div></Card></div>
  return <EmptyState title="Page not found" description="This page may have moved or is not available." action={<Link to="/owner/dashboard" className="fg-button fg-button--primary">Back to dashboard</Link>} />
}
function Settings() {
  const { user, roles, gym } = useOwner(); const [logout, setLogout] = useState(false); const mutation = useMutation()
  return <div className="ow-stack"><PageHeader title="Settings" description="Your profile and workspace preferences." /><Card title="Owner profile"><div className="ow-profile-summary"><span className="ow-avatar">{user.first_name?.[0] || <Icon name="user" />}</span><div><h2>{[user.first_name, user.last_name].filter(Boolean).join(' ') || 'Your account'}</h2><p>{user.email}</p></div></div><dl className="ow-details"><div><dt>Mobile</dt><dd>{user.phone || 'Not provided'}</dd></div><div><dt>Account roles</dt><dd>{roles.join(', ').replace(/_/g, ' ')}</dd></div><div><dt>Selected gym</dt><dd>{gym?.name || 'No gym selected'}</dd></div></dl><AccountProfileEditor user={user} /><NotificationCenter inbox={false} /></Card><Card title="Gym preferences"><p className="ow-muted">Update your gym details, photos, pricing and operating hours from its management page.</p><div className="ow-actions"><Link to={gym ? `/owner/gyms/${gym.id}` : '/owner/gyms'} className="fg-button fg-button--secondary">Manage gym</Link></div></Card><ChangePassword /><Card title="Account security"><p className="ow-muted">Sign out on shared devices when you have finished your work.</p><div className="ow-actions"><Button variant="danger" onClick={() => setLogout(true)}><Icon name="logout" />Sign out</Button></div></Card>{logout && <ConfirmDialog title="Sign out of FitiGo?" label="Sign out" destructive pending={mutation.pending} error={mutation.error} onClose={() => setLogout(false)} onConfirm={() => void mutation.run(async () => { await logoutSession() })}>Your server session will be revoked and your sign-in tokens removed from this device.</ConfirmDialog>}</div>
}
function More() {
  const { gymId, roles } = useOwner()
  return <div className="ow-stack"><PageHeader title="Your workspace" description="Everything you need to manage your gym." /><Card><div className="ow-quick-actions">{ownerLinks(gymId).filter(l => roles.includes('GYM_OWNER') || ['Settings', 'Check-in'].includes(l.label)).map(l => <Link to={l.to} key={l.label}><span className="ow-icon-tile"><Icon name={l.icon} /></span><strong>{l.label}</strong><Icon name="chevron" size={18} /></Link>)}</div></Card></div>
}