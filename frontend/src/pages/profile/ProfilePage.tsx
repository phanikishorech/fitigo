import { useState } from 'react'
import { logoutSession } from '../../session/store'
import { navigate } from '../../router'
import { useResource } from '../../hooks/useResource'
import { profileService } from '../../services/accountService'
import { Badge, Button, ErrorState, Heading, Image, Link, Modal, Skeleton } from '../../components/common/UI'
import Icon, { type IconName } from '../../components/common/Icon'

export default function ProfilePage() {
  const result = useResource(async () => { const [profile, user] = await Promise.all([profileService.get(), profileService.me()]); return { profile, user } }, 'profile')
  const [logout, setLogout] = useState(false)
  const rows: { title: string; subtitle: string; to: string; icon: IconName }[] = [
    { title: 'Membership', subtitle: 'Your plans and benefits', to: '/profile/membership', icon: 'ticket' },
    { title: 'Today’s access', subtitle: 'Your QR for gym entry', to: '/access/qr', icon: 'qr' },
    { title: 'Upcoming visits', subtitle: 'Make room for your next workout', to: '/bookings', icon: 'calendar' },
    { title: 'Visit history', subtitle: 'Look back at your workouts', to: '/profile/visits', icon: 'clock' },
    { title: 'Check-in history', subtitle: 'Your verified gym entries', to: '/profile/history', icon: 'check' },
    { title: 'Wallet', subtitle: 'Balance and transactions', to: '/wallet', icon: 'wallet' },
    { title: 'My reviews', subtitle: 'Share feedback after your visit', to: '/profile/reviews', icon: 'star' },
    { title: 'Settings', subtitle: 'Account and accessibility', to: '/settings', icon: 'user' }
  ]
  if (result.loading) return <Skeleton cards={2} />
  if (result.error) return <ErrorState message={result.error} retry={result.retry} />
  const { profile, user } = result.data!
  return <div className="fg-narrow"><Heading eyebrow="YOUR FITNESS. YOUR WAY." title="Your profile" /><section className="fg-panel fg-stack"><div className="fg-row"><span className="fg-avatar" style={{ width: 64, height: 64 }}>{profile.profile_image ? <Image src={profile.profile_image} alt={profile.full_name} /> : <Icon name="user" size={28} />}</span><div style={{ flex: 1 }}><h2>{profile.full_name}</h2><p className="fg-muted">{user.email || user.phone}</p></div><Badge tone={profile.membership_status === 'ACTIVE' ? 'success' : 'neutral'}>{profile.membership_status?.toLowerCase() ?? 'Member'}</Badge></div>{rows.map(row => <Link key={row.to} to={row.to} className="fg-list-row"><Icon name={row.icon} /><span><strong>{row.title}</strong><small>{row.subtitle}</small></span><Icon name="chevron" /></Link>)}<Button variant="text" onClick={() => setLogout(true)}><Icon name="logout" />Sign out</Button></section>{logout && <Modal title="Sign out of FitiGo?" onClose={() => setLogout(false)}><div className="fg-stack"><p>You can still explore gyms. Sign in again to book or access your membership.</p><Button onClick={() => { void logoutSession() }}>Sign out</Button><Button variant="secondary" onClick={() => setLogout(false)}>Stay signed in</Button></div></Modal>}</div>
}
export function SettingsPage() {
  return <div className="fg-narrow"><Heading title="Account settings" subtitle="Your preferences, kept simple." /><div className="fg-panel fg-stack"><h3>Profile details</h3><p className="fg-muted">Profile editing is not currently supported by the account service. Your verified contact details remain linked to your account.</p><h3>Accessibility</h3><p className="fg-muted">FitiGo follows your device’s reduced-motion preference and supports keyboard navigation.</p><h3>Location</h3><Link to="/location" className="fg-inline-link">Change your workout location <Icon name="arrow" size={18} /></Link><Link to="/profile" className="fg-inline-link">Back to profile</Link></div></div>
}