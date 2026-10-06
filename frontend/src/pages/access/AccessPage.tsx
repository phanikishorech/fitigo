import AccessQr from '../../components/AccessQr'
import { useEffect, useRef, useState } from 'react'
import { myAccessService } from '../../services/myAccessService'
import { MyAccessCard } from '../../components/membership/MyAccessCard'
import { navigate } from '../../router'
import { useMembershipResource } from '../../hooks/useMembershipResource'
import { useAccessQr } from '../../hooks/useAccessQr'
import { membershipDate, membershipTime, todayFrom, utcTimestamp } from '../../utils/membership'
import { Button, Heading, Link, Skeleton } from '../../components/common/UI'
import Icon from '../../components/common/Icon'
import { MembershipBack, MembershipNotice, MembershipPanel, MembershipStatusBadge } from '../../components/membership/MembershipUI'

export default function AccessPage() {
  const query = new URLSearchParams(window.location.search)
  const rawId = query.get('gymId')
  const gymId = Number(rawId)
  const selectedGym = Number.isSafeInteger(gymId) && gymId > 0 ? gymId : undefined
  const qr = !!selectedGym || query.get('generate') === '1'
  return <div className="fm-page fm-narrow">{qr ? <MembershipBack to="/my-access">My Access</MembershipBack> : <MembershipBack />}<Heading title={qr ? 'Your Access QR' : 'My Access'} subtitle={qr ? 'Your workout starts at the entrance.' : 'Your membership. Your access today.'} />{qr ? <QrCard key={selectedGym || 'daily'} gymId={selectedGym} /> : <AccessOverview />}</div>
}
function AccessOverview() {
  const resource = useMembershipResource(myAccessService.current, 'access-overview')
  const lock = useRef(false)
  const [generating, setGenerating] = useState(false)
  useEffect(() => {
    const refresh = () => { if (!document.hidden) resource.retry() }
    window.addEventListener('focus', refresh); document.addEventListener('visibilitychange', refresh)
    return () => { window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh) }
  }, [resource.retry])
  if (resource.loading) return <Skeleton cards={1} />
  if (resource.error || !resource.data) return <MembershipPanel><h2>Unable to load access status.</h2><p role="alert">{resource.error || 'Please try again.'}</p><Button onClick={resource.retry}>Retry</Button></MembershipPanel>
  return <MyAccessCard data={resource.data} refresh={resource.retry} generating={generating} generate={() => {
    if (lock.current) return
    lock.current = true; setGenerating(true)
    navigate('/access/qr?generate=1')
  }} />
}
function QrCard({ gymId }: { gymId?: number }) {
  const state = useAccessQr(gymId)
  const day = state.calendar ? todayFrom(state.calendar) : undefined
  if (state.loading) return <Skeleton cards={1} />
  if (state.error) return <MembershipPanel><div className="fm-centered"><span className="fm-icon fm-icon--large"><Icon name="shield" size={30} /></span><h2>{state.code === 'GYM_NOT_ELIGIBLE' ? 'This gym isn’t included' : state.code?.includes('ALREADY') ? 'Today’s Access Already Used' : state.code === 'MEMBERSHIP_PAUSED' ? 'Membership Paused' : state.code === 'MEMBERSHIP_EXPIRED' ? 'Membership Expired' : 'Unable to generate QR'}</h2><p role="alert">{state.error}</p><Button onClick={() => void state.refresh()}>Retry</Button><Link to="/membership" className="fg-button fg-button--secondary">View Membership</Link><Link to="/my-access" className="fm-back">Back to My Access</Link></div></MembershipPanel>
  if (state.checkedIn) return <MembershipPanel><div className="fm-centered fm-checkin-success"><span className="fm-success-icon"><Icon name="check" size={40} /></span><h2>Check-in Successful!</h2><p>Your workout is officially underway.</p><strong>{state.access?.status === 'USED' ? state.access.gym_name : day?.gym_name}</strong>{day && <p>{membershipDate(day.date)}{day.checkin_time ? ` · ${day.checkin_time.slice(0, 5)} UTC` : ''}</p>}<MembershipStatusBadge status="USED" /><p className="fm-muted">Today’s access has been used. Check your next daily access tomorrow; your membership must still be eligible.</p><Link to="/membership" className="fg-button fg-button--primary fm-full">View Membership</Link><Link to="/home" className="fg-button fg-button--secondary fm-full">Back to Home</Link></div></MembershipPanel>
  if (state.access?.status === 'USED') return <MembershipPanel><div className="fm-centered"><span className="fm-icon fm-icon--large"><Icon name="check" size={30} /></span><h2>Today’s Access Already Used</h2><p>You have already used your FitiGo access today.</p><strong>{state.access.gym_name}</strong><p>{membershipDate(state.access.used_at)} · {membershipTime(state.access.used_at)} UTC</p><MembershipStatusBadge status="USED" /><Link to="/membership" className="fg-button fg-button--primary fm-full">View Membership</Link><Link to="/home" className="fg-button fg-button--secondary fm-full">Back to Home</Link></div></MembershipPanel>
  if (state.access && state.access.status !== 'ACTIVE') return <MembershipPanel><div className="fm-centered"><MembershipStatusBadge status={state.access.status === 'NO_ACCESS' ? 'NOT_ACTIVE' : state.access.status} /><h2>{state.access.status === 'PAUSED' ? 'Membership Paused' : state.access.status === 'EXPIRED' ? 'Membership Expired' : 'Membership is not active.'}</h2><p>{state.access.status === 'PAUSED' ? 'Gym access is unavailable during a pause. Your daily access is not consumed.' : 'FitiGo has not issued access for today. Check your membership for more information.'}</p>{state.access.status === 'PAUSED' && state.details?.pause?.currently_paused && state.details.pause.current_pause && <MembershipNotice warning><p>Your membership is paused until: {membershipDate(state.details.pause.current_pause.end_date)}</p><p>Your access will automatically resume on {membershipDate(state.details.pause.current_pause.resumes_on)}.</p></MembershipNotice>}<Link to="/membership" className="fg-button fg-button--primary">View Membership</Link><Link to="/my-access" className="fg-button fg-button--secondary">Back to My Access</Link></div></MembershipPanel>
  if (state.needsRefresh) return <MembershipPanel><div className="fm-centered"><Icon name="qr" size={40} /><h2>Refresh your access QR</h2><p>Your QR was hidden or reached its server-provided expiry. Check your access again before entering.</p><Button onClick={() => void state.refresh()}>Refresh access</Button><Link to="/membership">View Membership</Link></div></MembershipPanel>
  if (state.access?.status === 'ACTIVE') {
    const expires = Date.parse(utcTimestamp(state.access.expires_at))
    if (!Number.isFinite(expires) || expires <= state.clock) return <MembershipPanel><h2>Your QR needs refreshing</h2><Button onClick={() => void state.refresh()}>Refresh access</Button></MembershipPanel>
    return <MembershipPanel className="fm-qr-card"><div className="fm-centered"><MembershipStatusBadge status="AVAILABLE" /><h2><Icon name="check" /> Access QR</h2><strong>{[state.details?.customer.first_name, state.details?.customer.last_name].filter(Boolean).join(' ') || 'FitiGo member'}</strong><p>{state.access.access_type === 'MULTI_GYM' ? 'FitiGo Multi-Gym' : 'Single-Gym'}</p><h3>{state.access.access_type === 'MULTI_GYM' ? 'Valid at eligible FitiGo gyms' : state.access.gym?.name}</h3>{state.access.access_type === 'SINGLE_GYM' && state.gym && <p className="fm-muted">{state.gym.location.full_address || [state.gym.location.locality, state.gym.location.city].filter(Boolean).join(', ')}</p>}<div className="fm-qr-frame"><AccessQr token={state.access.qr_token} /></div><strong>Show this QR to gym staff</strong><p className="fm-qr-validity"><Icon name="clock" size={17} />Valid for today only</p><p>This QR can only be used once today.</p><small className="fm-muted">QR expires at {membershipTime(state.access.expires_at)} UTC · {Math.max(0, Math.ceil((expires - state.clock) / 1000))} seconds remaining</small></div><MembershipNotice>Keep this screen open while staff scan. We check for a recorded check-in automatically. Never share your personal access QR.</MembershipNotice>{state.access.access_type === 'MULTI_GYM' && <p className="fm-footnote">Use this daily access QR at an eligible FitiGo gym. Staff validate entry for the scanning gym.</p>}<Link to="/my-access" className="fg-button fg-button--secondary fm-full">Back to My Access</Link></MembershipPanel>
  }
  return state.details && state.calendar ? <MyAccessCard data={{ ...state.details, calendar: state.calendar }} refresh={() => void state.refresh()} /> : <MembershipPanel><h2>Unable to load access status.</h2><Button onClick={() => void state.refresh()}>Retry</Button></MembershipPanel>
}