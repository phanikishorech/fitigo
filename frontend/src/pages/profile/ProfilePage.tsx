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
    { title: 'My bookings', subtitle: 'Your individual gym bookings and feedback', to: '/bookings', icon: 'calendar' },
    ...(result.data?.profile.has_membership_history ? [{ title: 'Membership visit history', subtitle: 'Your verified Single-Gym and Multi-Gym visits', to: '/profile/visits', icon: 'clock' as IconName }] : []),
    { title: 'Wallet', subtitle: 'Balance and transactions', to: '/wallet', icon: 'wallet' },
    { title: 'Payment history', subtitle: 'Recharges, bookings, memberships and refunds', to: '/profile/payments', icon: 'wallet' },
    { title: 'My reviews', subtitle: 'Share feedback after your visit', to: '/profile/reviews', icon: 'star' },
    { title: 'Settings', subtitle: 'Account and accessibility', to: '/settings', icon: 'user' }
  ]
  if (result.loading) return <Skeleton cards={2} />
  if (result.error) return <ErrorState message={result.error} retry={result.retry} />
  const { profile, user } = result.data!
  return <div className="fg-narrow"><Heading eyebrow="YOUR FITNESS. YOUR WAY." title="Your profile" /><section className="fg-panel fg-stack"><div className="fg-row"><span className="fg-avatar" style={{ width: 64, height: 64 }}>{profile.profile_image ? <Image src={profile.profile_image} alt={profile.full_name} /> : <Icon name="user" size={28} />}</span><div style={{ flex: 1 }}><h2>{profile.full_name}</h2><p className="fg-muted">{user.email || user.phone}</p></div><Badge tone={profile.membership_status === 'ACTIVE' ? 'success' : 'neutral'}>{profile.membership_status?.toLowerCase() ?? 'Member'}</Badge></div>{rows.map(row => <Link key={row.to} to={row.to} className="fg-list-row"><Icon name={row.icon} /><span><strong>{row.title}</strong><small>{row.subtitle}</small></span><Icon name="chevron" /></Link>)}<Button variant="text" onClick={() => setLogout(true)}><Icon name="logout" />Sign out</Button></section>{logout && <Modal title="Sign out of FitiGo?" onClose={() => setLogout(false)}><div className="fg-stack"><p>You can still explore gyms. Sign in again to book or access your membership.</p><Button onClick={() => { void logoutSession() }}>Sign out</Button><Button variant="secondary" onClick={() => setLogout(false)}>Stay signed in</Button></div></Modal>}</div>
}
