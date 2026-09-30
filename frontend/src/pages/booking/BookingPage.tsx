import { useEffect } from 'react'
import { getAccessToken } from '../../auth'
import { openAuthModal } from '../../authUi'
import { useMutation, useResource } from '../../hooks/useResource'
import { bookingService } from '../../services/bookingService'
import { localDate, money } from '../../services/client'
import { useBookingDraft } from '../../store/bookingStore'
import { navigate } from '../../router'
import { Alert, Button, EmptyState, ErrorState, Heading, Link, Skeleton } from '../../components/common/UI'
import Icon from '../../components/common/Icon'
import { isBookableSession } from '../../utils/booking'

export default function BookingPage({ gymId, schedule }: { gymId: number; schedule: boolean }) {
  const [draft, update] = useBookingDraft(gymId)
  const options = useResource(() => bookingService.options(gymId), String(gymId))
  const availability = useResource(async () => {
    const hours = await bookingService.hours(gymId, draft.date)
    const sessions = draft.accessType === 'CLASS' ? await bookingService.sessions(gymId, draft.date) : []
    return { hours, sessions }
  }, `${gymId}:${draft.date}:${draft.accessType}`)
  const mutation = useMutation()
  useEffect(() => { if (new URLSearchParams(window.location.search).get('type') === 'CLASS' && options.data?.has_classes) update({ accessType: 'CLASS' }) }, [gymId, options.data?.has_classes])
  if (options.loading) return <Skeleton cards={2} />
  if (options.error) return <ErrorState message={options.error} retry={options.retry} />
  const selected = availability.data?.sessions.find(s => s.id === draft.classId)
  const price = draft.accessType === 'GYM' ? options.data?.gym_price_per_person : selected?.price_per_person
  const max = draft.accessType === 'CLASS' && selected ? Math.min(50, selected.available_capacity) : 50
  const add = () => mutation.run(async () => {
    if (!getAccessToken()) { openAuthModal(window.location.pathname); return }
    if (draft.date < localDate()) throw new Error('Please choose today or a future date.')
    if (!Number.isInteger(draft.memberCount) || draft.memberCount < 1 || draft.memberCount > max) throw new Error('Please check the number of members.')
    if (draft.accessType === 'GYM') {
      if (!availability.data || availability.data.hours.is_closed) throw new Error('This gym is closed on your selected date.')
      if (!draft.start || !draft.end || draft.end <= draft.start) throw new Error('Choose an end time after your start time.')
      await bookingService.addGym({ booking_type: 'GYM', gym_id: gymId, booking_date: draft.date, preferred_start_time: draft.start, preferred_end_time: draft.end, member_count: draft.memberCount })
    } else {
      if (!selected || selected.available_capacity < draft.memberCount || !isBookableSession(selected.status, selected.available_capacity)) throw new Error('That session is no longer available. Choose another time.')
      await bookingService.addClass({ booking_type: 'CLASS', gym_id: gymId, booking_date: draft.date, class_session_id: selected.id, member_count: draft.memberCount })
    }
    navigate('/cart')
  })
  return <><Link to={`/gyms/${gymId}`} className="fg-inline-link"><Icon name="back" />{options.data?.gym_name}</Link><Heading eyebrow="YOUR NEXT WORKOUT" title={schedule ? 'Make time for yourself' : 'How do you want to work out?'} subtitle="Choose your visit. We’ll take care of the next step." /><div className="fg-stepper"><strong>01 Access</strong><Icon name="chevron" size={15} /><strong>{schedule ? '02 Schedule' : ''}</strong><span>{schedule ? '' : '02 Schedule'}</span><Icon name="chevron" size={15} /><span>03 Checkout</span></div><div className="fg-two-column"><div className="fg-panel fg-stack">
    {!schedule ? <><button className={`fg-plan ${draft.accessType === 'GYM' ? 'is-active' : ''}`} aria-pressed={draft.accessType === 'GYM'} onClick={() => update({ accessType: 'GYM', classId: null })}><div className="fg-row"><Icon name="gym" size={28} />{draft.accessType === 'GYM' && <Icon name="check" />}</div><h3>Gym access</h3><p className="fg-muted">Find your rhythm. Access the gym facilities.</p></button>{options.data?.has_classes && <button className={`fg-plan ${draft.accessType === 'CLASS' ? 'is-active' : ''}`} aria-pressed={draft.accessType === 'CLASS'} onClick={() => update({ accessType: 'CLASS' })}><div className="fg-row"><Icon name="spark" size={28} />{draft.accessType === 'CLASS' && <Icon name="check" />}</div><h3>Join a class</h3><p className="fg-muted">Move together. Choose an available session.</p></button>}<Button onClick={() => navigate(`/gyms/${gymId}/book/schedule`)}>Continue <Icon name="arrow" /></Button></> : <><label className="fg-field">Select date<input type="date" min={localDate()} value={draft.date} onChange={e => { if (e.target.value) update({ date: e.target.value, classId: null, start: '', end: '' }) }} /></label>{availability.loading ? <Skeleton cards={1} /> : availability.error ? <ErrorState message={availability.error} retry={availability.retry} /> : draft.accessType === 'GYM' ? availability.data?.hours.is_closed ? <Alert>This gym is closed on this date. Choose another day.</Alert> : <><p className="fg-muted">Open {availability.data?.hours.open_time?.slice(0, 5)} – {availability.data?.hours.close_time?.slice(0, 5)}</p><div className="fg-row"><label className="fg-field">Preferred start<input type="time" required min={availability.data?.hours.open_time?.slice(0, 5)} max={availability.data?.hours.close_time?.slice(0, 5)} value={draft.start} onChange={e => update({ start: e.target.value })} /></label><label className="fg-field">Preferred end<input type="time" required value={draft.end} min={draft.start} max={availability.data?.hours.close_time?.slice(0, 5)} onChange={e => update({ end: e.target.value })} /></label></div></> : availability.data?.sessions.length ? <div className="fg-stack"><h3>Choose a session</h3>{availability.data.sessions.map(session => <button key={session.id} disabled={!isBookableSession(session.status, session.available_capacity)} aria-pressed={draft.classId === session.id} className={`fg-plan ${draft.classId === session.id ? 'is-active' : ''}`} onClick={() => update({ classId: session.id, memberCount: Math.min(draft.memberCount, session.available_capacity) })}><h3>{session.class_name}</h3><p>{session.start_time.slice(0, 5)} – {session.end_time.slice(0, 5)}</p><p className="fg-muted">{session.available_capacity} seats available · {money(session.price_per_person)}</p></button>)}</div> : <EmptyState title="No classes on this date" description="Choose another date or explore gym access." />}<div className="fg-row"><div><h3>Members</h3><small className="fg-muted">You and your workout crew</small></div><div className="fg-counter"><Button variant="secondary" aria-label="Remove one member" disabled={draft.memberCount <= 1} onClick={() => update({ memberCount: draft.memberCount - 1 })}>−</Button><output aria-live="polite">{draft.memberCount}</output><Button variant="secondary" aria-label="Add one member" disabled={draft.memberCount >= max} onClick={() => update({ memberCount: draft.memberCount + 1 })}>+</Button></div></div>{mutation.error && <Alert>{mutation.error}</Alert>}<Button loading={mutation.pending} disabled={availability.loading || !!availability.error || (draft.accessType === 'GYM' ? !draft.start || !draft.end || availability.data?.hours.is_closed : !selected || selected.available_capacity < 1)} onClick={add}>Check availability & add to cart</Button><small className="fg-muted">The gym validates your selection when it is added. Nothing is charged until you confirm payment.</small><Link to={`/gyms/${gymId}/book/access`} className="fg-inline-link">Change access type</Link></>}
    </div><aside className="fg-panel fg-stack"><h3>Your visit</h3><p>{options.data?.gym_name}</p><p className="fg-muted">{draft.accessType === 'GYM' ? 'Gym access' : selected?.class_name ?? 'Class access'} · {draft.memberCount} {draft.memberCount === 1 ? 'member' : 'members'}</p>{price != null ? <><hr className="fg-divider" /><p>{money(price)} × {draft.memberCount} members</p><div className="fg-total-row"><strong>Estimated total</strong><strong>{money(Number(price) * draft.memberCount)}</strong></div></> : <p className="fg-muted">Choose a session to see pricing.</p>}<small className="fg-muted">Final pricing is provided by the gym and confirmed in your cart.</small></aside></div></>
}