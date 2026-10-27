import { useEffect } from 'react'
import { useSession } from '../../session/SessionGuard'
import { useMembershipResource } from '../../hooks/useMembershipResource'
import { accessService, membershipService } from '../../services/accountService'
import { validateAccessCalendar } from '../../services/myAccessService'
import { memberHomePresentation } from '../../utils/memberHome'
import { Badge, Button, Link } from '../common/UI'
import Icon from '../common/Icon'
import './homeMembership.css'

export default function HomeMembershipCard() {
  const session = useSession()
  if (session.status !== 'authenticated' || !session.identity.roles.some(role => ['CUSTOMER', 'USER'].includes(role))) return null
  return <MemberCard key={session.identity.user.id} userId={session.identity.user.id} />
}

function MemberCard({ userId }: { userId: number }) {
  const resource = useMembershipResource(async () => {
    const summary = await membershipService.summary()
    if (!summary.membership_id || !['ACTIVE', 'PAUSED'].includes(summary.status || '')) return null
    const calendar = await accessService.current()
    validateAccessCalendar(calendar)
    return memberHomePresentation(summary, calendar)
  }, `home-membership:${userId}`)
  useEffect(() => {
    const refresh = () => { if (!document.hidden) resource.retry() }
    window.addEventListener('focus', refresh); document.addEventListener('visibilitychange', refresh)
    return () => { window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh) }
  }, [resource.retry])
  if (resource.loading) return <section className="fg-panel fg-home-member" aria-label="Loading membership status" aria-busy="true"><p>Checking your membership…</p></section>
  if (resource.error) return <section className="fg-panel fg-home-member" aria-label="Membership status"><div><strong>Unable to check your membership right now</strong><p className="fg-muted">You can still explore gyms. Retry to see your membership access.</p></div><Button variant="secondary" onClick={resource.retry}>Retry membership status</Button></section>
  if (!resource.data) return null
  const card = resource.data
  return <section className="fg-panel fg-home-member" aria-label="Your membership access">
    <span className="fg-home-member-icon" aria-hidden="true"><Icon name="ticket" size={26} /></span>
    <div className="fg-home-member-copy"><Badge tone={card.status === 'Available today' ? 'success' : card.status === 'Paused' ? 'warning' : 'neutral'}>{card.status}</Badge><h2>{card.title}</h2><p>{card.message}</p></div>
    <Link to="/my-access" className="fg-button fg-button--primary">{card.action}<Icon name="arrow" size={18} /></Link>
  </section>
}