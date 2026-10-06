import type { ReactNode } from 'react'
import type { MyAccessData } from '../../services/myAccessService'
import { dayPresentation, membershipDate, todayFrom } from '../../utils/membership'
import { Button, Link } from '../common/UI'
import Icon from '../common/Icon'
import { MembershipFacts, MembershipNotice, MembershipPanel, MembershipStatusBadge } from './MembershipUI'

export function MyAccessCard({ data, refresh, generate, generating = false }: { data: MyAccessData; refresh: () => void; generate?: () => void; generating?: boolean }) {
  const { calendar, summary, type, gym, pause } = data
  const day = todayFrom(calendar)!
  const presentation = dayPresentation(day)
  const used = presentation === 'USED' || presentation === 'VISITED'
  const available = presentation === 'AVAILABLE'
  const paused = presentation === 'PAUSED'
  const expired = presentation === 'EXPIRED' || (day.qr_status === 'NO_ACCESS' && summary.status === 'EXPIRED')
  const status = used ? 'USED' : available ? 'AVAILABLE' : paused ? 'PAUSED' : expired ? 'EXPIRED' : 'NOT_ACTIVE'
  return <div className="fm-access-stack">
    <MembershipPanel className="fm-access-card">
      <div className="fm-panel-heading"><h2>Today’s Access</h2><MembershipStatusBadge status={status} /></div>
      <h3 className="fm-access-title">{available ? 'Your next workout is waiting.' : used ? 'You’ve used your access today.' : paused ? 'Membership Paused' : expired ? 'Membership Expired' : 'Membership is not active.'}</h3>
      <p className="fm-muted">{membershipDate(day.date)} · Access day uses UTC</p>
      {available && <><p>{type === 'MULTI_GYM' ? 'Your daily access is ready.' : 'Your membership access is ready.'}</p><Button className="fm-full" loading={generating} disabled={!generate} onClick={generate}><Icon name="qr" size={20} />Generate Visit QR</Button></>}
      {used && <><p>Your daily access has already been used today.</p>{day.gym_name && <div className="fm-visit-mini"><Icon name="gym" /><span><strong>{day.gym_name}</strong>{day.checkin_time && <small>{day.checkin_time.slice(0, 5)} UTC · Validated</small>}</span></div>}<p className="fm-muted">Check your next daily access tomorrow. Your membership must still be eligible.</p></>}
      {paused && <MembershipNotice warning><strong>Your membership is currently paused.</strong>{pause?.currently_paused && pause.current_pause && <><p>Your membership is paused until: {membershipDate(pause.current_pause.end_date)}</p><p>Resumes {membershipDate(pause.current_pause.resumes_on)}.</p></>}<p>Your access will automatically resume after the pause period.</p><p>Gym access is unavailable during a pause. Daily access is not consumed.</p></MembershipNotice>}
      {expired && <p>Your membership has expired. View your membership options to continue.</p>}
      {!available && !used && !paused && !expired && <p>Check your membership for available plans and access details.</p>}
      {type === 'SINGLE_GYM' && gym && <section className="fm-access-gym" aria-label="Assigned membership gym"><span className="fm-eyebrow">MY GYM</span><div className="fm-access-gym-heading"><Icon name="gym" size={23} /><h3>{gym.gym_name}</h3></div>{(gym.location.full_address || gym.location.locality || gym.location.city) && <p className="fm-muted">{gym.location.full_address || [gym.location.locality, gym.location.city].filter(Boolean).join(', ')}</p>}<p>Your membership is valid at this gym{available ? '.' : ' when active.'}</p></section>}
      {available && type === 'MULTI_GYM' && <div className="fm-access-discovery"><p>Your daily access can be used at any eligible FitiGo gym.</p><Link to="/gyms" className="fg-button fg-button--secondary fm-full">Find a Gym<Icon name="arrow" size={18} /></Link></div>}
      <MembershipFacts rows={[
        ...(type === 'MULTI_GYM' || type === 'SINGLE_GYM' ? [['Membership', type === 'MULTI_GYM' ? 'FitiGo Multi-Gym' : 'Single-Gym']] as [string, string][] : []),
        ...(summary.status ? [['Membership status', <MembershipStatusBadge status={summary.status} />]] as [string, ReactNode][] : []),
        ...(summary.end_date ? [['Membership valid until', membershipDate(summary.end_date)]] as [string, string][] : []),
      ]} />
      <p className="fm-footnote">{type === 'MULTI_GYM' ? 'One daily access per active day. Unused daily access does not carry forward.' : 'Your personal membership access is validated by gym staff.'}</p>
      {!available && <Link to="/membership" className="fg-button fg-button--secondary fm-full">View Membership</Link>}
    </MembershipPanel>
    <Button variant="text" className="fm-access-refresh" onClick={refresh} disabled={generating}>Refresh access status</Button>
  </div>
}