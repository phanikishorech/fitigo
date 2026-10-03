import type { ReactNode } from 'react'
import { Button, ErrorState, Link, Skeleton } from '../common/UI'
import Icon from '../common/Icon'
import type { AccessCalendar, AccessDay } from '../../services/accountService'
import { accessLabels, dayPresentation, membershipDate, todayFrom } from '../../utils/membership'
import '../../membership.css'

export function MembershipStatusBadge({ status }: { status: string }) {
  const tone = ['ACTIVE', 'AVAILABLE', 'VISITED', 'VALID', 'CHECKED_IN'].includes(status) ? 'success' : ['PAUSED', 'PENDING'].includes(status) ? 'warning' : ['EXPIRED', 'CANCELLED', 'INVALID_QR', 'UNAVAILABLE'].includes(status) ? 'danger' : 'neutral'
  const labels: Record<string, string> = { AVAILABLE: 'Available', ACTIVE: 'Active', PAUSED: 'Paused', USED: 'Used', VISITED: 'Visited', EXPIRED: 'Expired', CONSUMED: 'Access consumed', CHECKED_IN: 'Validated', SINGLE_GYM: 'Single-gym', MULTI_GYM: 'Multi-gym' }
  return <span className={`fm-status fm-status--${tone}`}><span aria-hidden="true">{tone === 'success' ? '✓' : tone === 'warning' ? 'Ⅱ' : '•'}</span>{labels[status] || status.replaceAll('_', ' ').toLowerCase()}</span>
}
export function MembershipPanel({ title, children, className = '', action }: { title?: string; children: ReactNode; className?: string; action?: ReactNode }) {
  return <section className={`fm-panel ${className}`}>{title && <div className="fm-panel-heading"><h2>{title}</h2>{action}</div>}{children}</section>
}
export function MembershipFacts({ rows }: { rows: [string, ReactNode][] }) { return <dl className="fm-facts">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl> }
export function MembershipNotice({ children, warning = false }: { children: ReactNode; warning?: boolean }) {
  return <div className={`fm-notice${warning ? ' fm-notice--warning' : ''}`}><Icon name={warning ? 'clock' : 'shield'} size={19} /><div>{children}</div></div>
}
export function MembershipResource<T>({ resource, children }: { resource: { loading: boolean; error: string; data: T | null; retry: () => void }; children: (data: T) => ReactNode }) {
  if (resource.loading) return <Skeleton cards={2} />
  if (resource.error) return <ErrorState message={resource.error} retry={resource.retry} />
  return <>{resource.data !== null && children(resource.data)}</>
}
export function MembershipBack({ to = '/membership', children = 'My membership' }: { to?: string; children?: ReactNode }) { return <Link to={to} className="fm-back"><Icon name="back" size={18} />{children}</Link> }
export function DailyAccessCard({ calendar, refresh, compact = false }: { calendar: AccessCalendar; refresh?: () => void; compact?: boolean }) {
  const day = todayFrom(calendar)
  const state = day ? dayPresentation(day) : 'UNAVAILABLE'
  const available = state === 'AVAILABLE'; const used = state === 'USED' || state === 'VISITED'
  return <MembershipPanel className={`fm-daily fm-daily--${state.toLowerCase()}`}><div className="fm-panel-heading"><span className="fm-icon"><Icon name={used ? 'check' : state === 'PAUSED' ? 'clock' : 'qr'} size={23} /></span><MembershipStatusBadge status={used ? 'USED' : state} /></div><h2>Today’s Access</h2><p className="fm-daily-title">{available ? 'Your next workout is waiting.' : used ? 'You’ve used your access today.' : state === 'PAUSED' ? 'A little pause. A fresh start.' : state === 'EXPIRED' ? 'Your access has expired.' : 'No access available today.'}</p>{day && <small className="fm-muted">{membershipDate(day.date)} · Access day uses UTC</small>}{used && <><p>You have already used your FitiGo access today.</p>{day?.gym_name && <div className="fm-visit-mini"><Icon name="gym" /><span><strong>{day.gym_name}</strong>{day.checkin_time && <small>{day.checkin_time.slice(0, 5)} UTC · Validated</small>}</span></div>}<p className="fm-muted">You can check your next daily access tomorrow. Membership eligibility is verified again then.</p></>}{state === 'PAUSED' && <MembershipNotice warning>Gym access is unavailable during a pause. Daily access is not consumed on paused days.</MembershipNotice>}{available && <><p>One gym access per active day. Unused daily access does not carry forward.</p><Link to={calendar.access_type === 'SINGLE_GYM' && calendar.gym ? `/gyms/${calendar.gym.id}/visit` : '/gyms'} className="fg-button fg-button--primary">{calendar.access_type === 'SINGLE_GYM' ? 'Plan today’s visit' : 'Find a Gym'}<Icon name="arrow" size={18} /></Link></>}{!available && !compact && <Link to="/membership" className="fg-button fg-button--secondary">View Membership</Link>}{refresh && <Button variant="text" onClick={refresh}>Refresh access status</Button>}</MembershipPanel>
}
export function AccessDayDetail({ day }: { day: AccessDay }) {
  const state = dayPresentation(day)
  return <div className="fm-day-detail" role="status"><div className="fm-panel-heading"><strong>{membershipDate(day.date)}</strong><MembershipStatusBadge status={state} /></div><p>{accessLabels[state]}</p>{day.gym_name && <p><Icon name="gym" size={17} /> {day.gym_name}</p>}{day.checkin_time && <small>Validated at {day.checkin_time.slice(0, 5)} UTC</small>}{state === 'CONSUMED' && <small>No gym visit was recorded. This active day’s access did not carry forward.</small>}{state === 'PAUSED' && <small>Gym access was paused. Daily access was not consumed.</small>}</div>
}
export function PauseUnavailable() {
  return <div className="fm-page fm-narrow"><MembershipBack /><MembershipPanel><div className="fm-centered"><span className="fm-icon fm-icon--large"><Icon name="calendar" size={30} /></span><h1>Pause Membership</h1><p className="fm-muted">Take a break without losing sight of your routine.</p></div><MembershipNotice warning>Pause scheduling is not available for your account in this version of FitiGo. No dates have been paused and your membership expiry has not changed.</MembershipNotice><p>Verified plan allowances, eligible dates and a server-confirmed expiry are required before a pause can be requested.</p><Link to="/membership" className="fg-button fg-button--primary fm-full">View Membership</Link></MembershipPanel></div>
}
export function NoMembership() {
  return <section className="fm-membership-choices" aria-labelledby="membership-choices-title">
    <div className="fm-choice-heading"><h2 id="membership-choices-title">Your next chapter starts here</h2><p>Choose how you want to work out with FitiGo.</p></div>
    <div className="fm-choice-grid">
      <MembershipPanel className="fm-choice-card fm-choice-card--multi">
        <span className="fm-icon"><Icon name="gym" size={25} /></span>
        <h3>Multi-Gym Membership</h3><p className="fm-choice-description">One membership. Multiple gyms.</p>
        <p className="fm-choice-info">Access eligible FitiGo partner gyms with one membership.</p>
        <Link to="/membership/multi-gym/plans" className="fg-button fg-button--primary">View Multi-Gym Plans<Icon name="arrow" size={18} /></Link>
      </MembershipPanel>
      <MembershipPanel className="fm-choice-card">
        <span className="fm-icon"><Icon name="pin" size={25} /></span>
        <h3>Single-Gym Membership</h3><p className="fm-choice-description">Have a regular gym in mind?</p>
        <p className="fm-choice-info">Explore FitiGo gyms and choose a membership for a specific gym.</p>
        <Link to="/explore" className="fg-button fg-button--secondary">Explore Gyms<Icon name="arrow" size={18} /></Link>
      </MembershipPanel>
    </div>
  </section>
}