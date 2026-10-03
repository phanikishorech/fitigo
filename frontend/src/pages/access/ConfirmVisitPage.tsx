import { useEffect } from 'react'
import { visitAccessService } from '../../services/visitAccessService'
import { useMembershipResource } from '../../hooks/useMembershipResource'
import { membershipDate, todayFrom } from '../../utils/membership'
import { Button, Heading, Image, Link } from '../../components/common/UI'
import Icon from '../../components/common/Icon'
import { DailyAccessCard, MembershipBack, MembershipFacts, MembershipNotice, MembershipPanel, MembershipResource, MembershipStatusBadge } from '../../components/membership/MembershipUI'

export default function ConfirmVisitPage({ gymId }: { gymId: number }) {
  const resource = useMembershipResource(() => visitAccessService.check(gymId), `my-access:${gymId}`)
  useEffect(() => {
    const refresh = () => { if (!document.hidden) resource.retry() }
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => { window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh) }
  }, [resource.retry])
  return <div className="fm-page fm-narrow"><MembershipBack to={`/gyms/${gymId}`}>Back to gym</MembershipBack><Heading title="My Access" subtitle="Your membership. Your visit today." />{resource.error ? <MembershipPanel><p role="alert">Unable to check your membership access.</p><Button onClick={resource.retry}>Try Again</Button></MembershipPanel> : <MembershipResource resource={resource}>{({ gym, calendar, decision }) => {
    if (decision === 'ALREADY_USED') return <DailyAccessCard calendar={calendar} refresh={resource.retry} />
    if (decision !== 'MEMBERSHIP') return <MembershipPanel><h2>Membership access isn’t available today</h2><p>Your membership does not currently cover today’s access at this gym.</p><Link to="/membership" className="fg-button fg-button--secondary">View Membership</Link><Button variant="text" onClick={resource.retry}>Refresh access status</Button></MembershipPanel>
    const day = todayFrom(calendar)!
    return <><MembershipPanel className="fm-confirm-gym"><Image src={gym.images[0]?.image_url} alt={gym.gym_name} /><div className="fm-confirm-body"><MembershipStatusBadge status="AVAILABLE" /><h2>{gym.gym_name}</h2><p className="fm-muted"><Icon name="pin" size={16} />{[gym.location.locality, gym.location.city].filter(Boolean).join(', ') || gym.location.full_address}</p>{gym.opening_hours.open_today && <p><Icon name="clock" size={16} />{gym.opening_hours.open_today}</p>}</div></MembershipPanel><MembershipPanel title="Your Access Today"><MembershipFacts rows={[["Selected gym", gym.gym_name], ['Membership', calendar.access_type === 'MULTI_GYM' ? 'FitiGo Multi-Gym' : 'Single-Gym'], ['Date', `${membershipDate(day.date)} · Today (UTC)`], ['Today’s access', <MembershipStatusBadge status="AVAILABLE" />]]} /><MembershipNotice>Your membership covers today’s visit. Show your personal QR to gym staff to validate your access.</MembershipNotice><Link to={`/access/qr?gymId=${gymId}`} className="fg-button fg-button--primary fm-full"><Icon name="qr" size={20} />Generate Visit QR</Link><Link to="/membership" className="fg-button fg-button--secondary fm-full">View Membership</Link></MembershipPanel></>
  }}</MembershipResource>}</div>
}