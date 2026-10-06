import { accessService, membershipService, type Membership, type MembershipSummary } from '../../services/accountService'
import { gymService } from '../../services/gymService'
import { useMembershipResource } from '../../hooks/useMembershipResource'
import { Button, Heading, Image, Link } from '../../components/common/UI'
import Icon from '../../components/common/Icon'
import { DailyAccessCard, MembershipBack, MembershipFacts, MembershipNotice, MembershipPanel, MembershipResource, MembershipStatusBadge, NoMembership } from '../../components/membership/MembershipUI'
import { membershipDate, membershipOverviewState } from '../../utils/membership'
import { createContext, useContext } from 'react'
import { MembershipPause } from '../../components/membership/MembershipPause'
const RefreshMembership = createContext<() => void>(() => {})

export default function MembershipOverview({ id, details = false, success = false }: { id?: number; details?: boolean; success?: boolean }) {
  const resource = useMembershipResource(async () => { const [memberships, summary] = await Promise.all([membershipService.mine(), membershipService.summary()]); return { memberships, summary } }, `membership:${id || 'all'}`)
  return <RefreshMembership.Provider value={resource.retry}><div className="fm-page">{id && <MembershipBack />}<Heading eyebrow="YOUR ROUTINE. YOUR WAY." title={details ? 'Membership Details' : 'My Membership'} subtitle={details ? 'Your plan, access and membership period.' : 'Everything you need for your next workout.'} action={<Link to="/profile/access" className="fg-button fg-button--secondary"><Icon name="calendar" size={18} />Access calendar</Link>} /><MembershipResource resource={resource}>{({ memberships, summary }) => {
    const selected = id ? memberships.find(item => item.id === id) : undefined
    if (id && !selected) return <MembershipPanel><h2>Membership not found</h2><p>This membership is not available on your account.</p><Link to="/membership" className="fg-button fg-button--primary">View your memberships</Link></MembershipPanel>
    const overviewState = membershipOverviewState(memberships, summary.status)
    if (!id && overviewState === 'none') return <><NoMembership />{memberships.length > 0 && <section className="fm-membership-history" aria-labelledby="membership-history-title"><h2 id="membership-history-title">Your membership records</h2><p className="fm-muted">Review your previous plans and their current status.</p><div className="fm-stack">{memberships.map(membership => <MembershipPanel key={membership.id}><div className="fm-panel-heading"><h3>{summary.membership_id === membership.id && summary.plan_name ? summary.plan_name : `Membership #${membership.id}`}</h3><MembershipStatusBadge status={membership.status} /></div><p className="fm-muted">{membershipDate(membership.start_at)} – {membershipDate(membership.end_at)}</p><Link to={`/membership/${membership.id}/details`} className="fg-button fg-button--text">Membership Details<Icon name="chevron" size={16} /></Link></MembershipPanel>)}</div></section>}</>
    if (!memberships.length) return <MembershipPanel><h2>Unable to display your membership</h2><p>Your membership summary and records could not be matched. Refresh to check your current information.</p><Button onClick={resource.retry}>Try again</Button></MembershipPanel>
    const purchased = memberships.find(item => item.id === Number(new URLSearchParams(window.location.search).get('id')))
    const primary = selected || memberships.find(membership => membership.status === 'ACTIVE') || memberships.find(membership => membership.status === 'PAUSED') || memberships[0]
    const multi = !id && primary.membership_type !== 'MULTI_GYM' && overviewState === 'active' && summary.status === 'ACTIVE' && summary.membership_scope === 'MULTI_GYM'
    return <>{success && purchased?.status === 'ACTIVE' && <MembershipNotice>Your membership is active. Your current plan information has been loaded from FitiGo.</MembershipNotice>}<div className={`fm-membership-layout${multi ? '' : ' fm-membership-layout--with-pause'}`}><div className="fm-primary-membership">{multi ? <MultiGymCard summary={summary} /> : <MembershipCardContent membership={primary} summary={summary} expanded={!!id} details={details} />}</div>{!multi && <div className="fm-primary-pause"><MembershipPauseCard membershipId={primary.id} /></div>}<aside className="fm-current-access"><CurrentAccess /></aside><div className="fm-stack fm-additional-memberships">{(selected ? [] : multi ? memberships : memberships.filter(membership => membership.id !== primary.id)).map(membership => <MembershipCard key={membership.id} membership={membership} summary={summary} expanded={false} details={false} />)}</div><aside className="fm-membership-links"><MembershipLinks multi={summary.membership_scope === 'MULTI_GYM'} /></aside></div></>
  }}</MembershipResource></div></RefreshMembership.Provider>
}
function MultiGymCard({ summary }: { summary: MembershipSummary }) {
  return <MembershipPanel className="fm-membership-card fm-membership-card--multi"><div className="fm-card-brand"><span><Icon name="gym" size={22} />FitiGo</span><MembershipStatusBadge status={summary.status || 'UNKNOWN'} /></div><div className="fm-membership-card-title"><span className="fm-eyebrow">MULTI-GYM ACCESS</span><h2>FitiGo Multi-Gym</h2>{summary.plan_name && <p>{summary.plan_name}</p>}</div><div className="fm-card-divider" /><MembershipFacts rows={[["Access", 'Eligible FitiGo partner gyms'], ['Daily access', '1 gym access per active day'], ...(summary.start_date && summary.end_date ? [['Reported membership period', `${membershipDate(summary.start_date)} – ${membershipDate(summary.end_date)}`] as [string, string]] : [])]} /><MembershipNotice>Your account has multi-gym access. Find a gym to see locations explicitly included by the membership service. Individual plan periods are listed below.</MembershipNotice></MembershipPanel>
}
function MembershipCard({ membership, summary, expanded, details }: { membership: Membership; summary: MembershipSummary; expanded: boolean; details: boolean }) {
  return <div className="fm-stack"><MembershipCardContent membership={membership} summary={summary} expanded={expanded} details={details} /><MembershipPauseCard membershipId={membership.id} /></div>
}
function MembershipPauseCard({ membershipId }: { membershipId: number }) {
  const refresh = useContext(RefreshMembership)
  return <MembershipPanel className="fm-pause-card"><MembershipPause membershipId={membershipId} onChanged={refresh} /></MembershipPanel>
}
function MembershipCardContent({ membership, summary, expanded, details }: { membership: Membership; summary: MembershipSummary; expanded: boolean; details: boolean }) {
  if (membership.membership_type === 'MULTI_GYM') return <MembershipPanel className="fm-membership-card"><div className="fm-card-brand"><span>Multi-Gym Access</span><MembershipStatusBadge status={membership.status} /></div><h2>{membership.terms_snapshot?.name || 'FitiGo Multi-Gym'}</h2><MembershipFacts rows={[
    ['Access', 'Eligible FitiGo partner gyms'], ['Daily access', '1 gym access per active day'],
    ['Membership period', `${membershipDate(membership.start_at)} – ${membershipDate(membership.end_at)}`],
    ['Payment', membership.payment_provider === 'WALLET' ? 'Wallet · Test credits' : membership.payment_status],
    ...(membership.terms_snapshot ? [['Plan duration', `${membership.terms_snapshot.duration_value} ${membership.terms_snapshot.duration_unit.toLowerCase()}`] as [string, string]] : []),
  ]} /><div className="fm-card-actions"><Link to={`/membership/${membership.id}/details`} className="fg-button fg-button--secondary">Membership Details</Link><Link to="/profile/visits" className="fg-button fg-button--text">Visit History</Link></div></MembershipPanel>
  return <SingleMembershipCard membership={membership} summary={summary} expanded={expanded} details={details} />
}
function SingleMembershipCard({ membership, summary, expanded, details }: { membership: Membership; summary: MembershipSummary; expanded: boolean; details: boolean }) {
  const information = useMembershipResource(async () => {
    if (membership.gym_id === null) return { gym: null, plan: null, partial: true }
    const [gym, plans] = await Promise.allSettled([gymService.details(membership.gym_id), membershipService.plans(membership.gym_id)])
    return { gym: gym.status === 'fulfilled' ? gym.value : null, plan: plans.status === 'fulfilled' ? plans.value.find(item => item.id === membership.plan_id) : null, partial: gym.status === 'rejected' || plans.status === 'rejected' }
  }, `membership-information:${membership.id}`)
  const gym = information.data?.gym; const plan = information.data?.plan
  const knownGym = summary.active_gyms.find(item => item.gym_id === membership.gym_id)
  const name = gym?.gym_name || knownGym?.gym_name || `Gym #${membership.gym_id}`
  const planName = plan?.name || (summary.membership_id === membership.id ? summary.plan_name : null) || `Plan #${membership.plan_id}`
  const location = gym ? [gym.location.locality, gym.location.city].filter(Boolean).join(', ') : [knownGym?.locality, knownGym?.city].filter(Boolean).join(', ')
  return <MembershipPanel className="fm-membership-card"><div className="fm-card-brand"><span><Icon name="ticket" size={22} />Single-Gym Access</span><MembershipStatusBadge status={membership.status} /></div><div className="fm-membership-card-title"><span className="fm-eyebrow">YOUR MEMBERSHIP</span><h2>{planName}</h2></div><div className="fm-gym-summary"><Image src={gym?.images[0]?.image_url} alt={name} /><div><h3>{name}</h3>{location && <p><Icon name="pin" size={15} />{location}</p>}</div></div><MembershipFacts rows={[["Membership period", `${membershipDate(membership.start_at)} – ${membershipDate(membership.end_at)}`], ['Gym access', 'This gym only'], ...(details ? [['Type', 'Single-Gym'], ['Membership ID', `#${membership.id}`], ...(plan ? [['Plan duration', `${plan.duration_days} days`]] : []), ['Start date', membershipDate(membership.start_at)], ['Current expiry', membershipDate(membership.end_at)], ['Payment status', membership.payment_status]] as [string, string][] : [])]} />{information.data?.partial && <MembershipNotice>Some gym or plan details are unavailable. Your membership record is still shown.<Button variant="text" onClick={information.retry}>Retry details</Button></MembershipNotice>}{membership.status === 'EXPIRED' && <MembershipNotice warning>Your FitiGo membership expired on {membershipDate(membership.end_at)}. <Link to={`/gyms/${membership.gym_id}/membership`}>View Plans</Link></MembershipNotice>}{membership.status === 'PAUSED' && <MembershipNotice warning>Gym access is unavailable during this pause. Your pause schedule and updated expiry are shown below.</MembershipNotice>}<div className="fm-card-actions"><Link to={`/gyms/${membership.gym_id}`} className="fg-button fg-button--secondary">View Gym<Icon name="arrow" size={17} /></Link><Link to={expanded && !details ? `/membership/${membership.id}/details` : `/membership/${membership.id}`} className="fg-button fg-button--text">{details ? 'Membership overview' : 'Membership Details'}<Icon name="chevron" size={16} /></Link></div></MembershipPanel>
}
function CurrentAccess() {
  const resource = useMembershipResource(accessService.current, 'membership-today')
  return <MembershipResource resource={resource}>{calendar => <DailyAccessCard calendar={calendar} refresh={resource.retry} compact />}</MembershipResource>
}
function MembershipLinks({ multi: _multi }: { multi: boolean }) {
  return <MembershipPanel title="Your membership, at a glance"><Link to="/profile/access" className="fm-menu-row"><Icon name="calendar" /><span><strong>Membership calendar</strong><small>Access days, visits and pauses</small></span><Icon name="chevron" size={17} /></Link><Link to="/profile/visits" className="fm-menu-row"><Icon name="clock" /><span><strong>Visit history</strong><small>Your validated gym check-ins</small></span><Icon name="chevron" size={17} /></Link><MembershipNotice>One daily access per active day. Access is shared across your memberships and does not accumulate.</MembershipNotice></MembershipPanel>
}