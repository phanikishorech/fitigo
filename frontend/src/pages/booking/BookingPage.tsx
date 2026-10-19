import { useEffect, useState } from 'react'
import { getAccessToken } from '../../auth'
import { openAuthModal } from '../../authUi'
import { useMutation, useResource } from '../../hooks/useResource'
import { bookingService } from '../../services/bookingService'
import { money } from '../../services/client'
import { useBookingDraft } from '../../store/bookingStore'
import { navigate } from '../../router'
import { Alert, Button, EmptyState, ErrorState, Heading, Link, Skeleton } from '../../components/common/UI'
import Icon from '../../components/common/Icon'
import { isBookableSession, isFutureBookingStart, gymStartOptions, oneHourVisitEnd, istDateKey } from '../../utils/booking'
import { visitAccessService } from '../../services/visitAccessService'
import { todayFrom } from '../../utils/membership'
import { usePendingAction } from '../../session/usePendingAction'

export default function BookingPage({ gymId, schedule, companionsDate }: { gymId: number; schedule: boolean; companionsDate?: string }) {
  const [draft, update] = useBookingDraft(gymId, companionsDate)
  const [visitors, setVisitors] = useState<string[]>([])
  const options = useResource(async () => ({ ...await bookingService.options(gymId), receivedAt: Date.now() }), String(gymId))
  const [clock, setClock] = useState(Date.now())
  useEffect(() => { const timer = setInterval(() => setClock(Date.now()), 1000); return () => clearInterval(timer) }, [])
  const bookingNow = (at: number) => {
    const server = Date.parse(options.data?.server_now || '')
    return Number.isFinite(server) ? server + Math.max(0, at - options.data!.receivedAt) : at
  }
  const now = bookingNow(clock)
  const today = istDateKey(now)
  const availability = useResource(async () => {
    const hours = await bookingService.hours(gymId, draft.date)
    const sessions = draft.accessType === 'CLASS' ? await bookingService.sessions(gymId, draft.date) : []
    return { hours, sessions }
  }, `${gymId}:${draft.date}:${draft.accessType}`)
  const mutation = useMutation()
  usePendingAction('ADD_TO_CART', () => add(), !!options.data && !!availability.data && !options.loading && !availability.loading && !options.error && !availability.error)
  useEffect(() => {
    if (!companionsDate && new URLSearchParams(window.location.search).get('type') === 'CLASS' && options.data?.has_classes) update({ accessType: 'CLASS' })
  }, [gymId, options.data?.has_classes, companionsDate])
  if (options.loading) return <Skeleton cards={2} />
  if (options.error) return <ErrorState message={options.error} retry={options.retry} />
  const selected = availability.data?.sessions.find(s => s.id === draft.classId)
  const starts = availability.data?.hours.is_closed ? [] : gymStartOptions(draft.date, availability.data?.hours.open_time, availability.data?.hours.close_time, now)
  const selectedHour = draft.start.slice(0, 2)
  const selectedMinute = draft.start.slice(3, 5)
  const hours = [...new Set(starts.map(start => start.slice(0, 2)))]
  const minutes = starts.filter(start => start.startsWith(`${selectedHour}:`)).map(start => start.slice(3, 5))
  const endTime = oneHourVisitEnd(draft.start)
  const startTime = draft.accessType === 'GYM' ? draft.start : selected?.start_time || ''
  const futureStart = isFutureBookingStart(draft.date, startTime, now)
  const price = draft.accessType === 'GYM' ? options.data?.gym_price_per_person : selected?.price_per_person
  const max = draft.accessType === 'CLASS' && selected ? Math.min(50, selected.available_capacity) : 50
  function add() { return mutation.run(async () => {
    if (!getAccessToken()) { openAuthModal({ action: 'ADD_TO_CART', metadata: { gymId: String(gymId) } }); return }
    if (companionsDate) {
      let access
      try { access = await visitAccessService.check(gymId) } catch { throw new Error('Unable to check your membership access. Please try again.') }
      if (access.decision !== 'MEMBERSHIP' || todayFrom(access.calendar)?.date !== companionsDate) {
        navigate(`/gyms/${gymId}/book/access`)
        return
      }
    }
    if (!isFutureBookingStart(draft.date, startTime, bookingNow(Date.now()))) throw new Error('Choose a future date and start time (IST).')
    if (!Number.isInteger(draft.memberCount) || draft.memberCount < 1 || draft.memberCount > max) throw new Error('Please check the number of members.')
    const visitor_names = Array.from({ length: draft.memberCount }, (_, index) => (visitors[index] || '').trim())
    if (visitor_names.some(name => !name || name.length > 150)) throw new Error('Enter the name of each person who will use the booking.')
    if (draft.accessType === 'GYM') {
      if (!availability.data || availability.data.hours.is_closed) throw new Error('This gym is closed on your selected date.')
      if (!starts.includes(draft.start) || !endTime) throw new Error('Choose an available quarter-hour start for a one-hour visit.')
      // In companion mode memberCount contains additional people only. The member's
      // QR entitlement is never submitted as a paid cart item or a fake discount.
      await bookingService.addGym({ booking_type: 'GYM', gym_id: gymId, booking_date: draft.date, preferred_start_time: draft.start, member_count: draft.memberCount, visitor_names })
    } else {
      if (!selected || selected.available_capacity < draft.memberCount || !isBookableSession(selected.status, selected.available_capacity)) throw new Error('That session is no longer available. Choose another time.')
      await bookingService.addClass({ booking_type: 'CLASS', gym_id: gymId, booking_date: draft.date, class_session_id: selected.id, member_count: draft.memberCount, visitor_names })
    }
    navigate('/cart')
  }) }
  return <>
    <Link to={`/gyms/${gymId}`} className="fg-inline-link"><Icon name="back" />{options.data?.gym_name}</Link>
    <Heading eyebrow="YOUR NEXT WORKOUT" title={companionsDate ? 'Add People' : schedule ? 'Make time for yourself' : 'How do you want to work out?'} subtitle={companionsDate ? 'Choose paid day visits for friends or family joining you today. Do not include yourself in the count.' : 'Choose your visit. We’ll take care of the next step.'} />
    <div className="fg-stepper"><strong>{companionsDate ? '01 People' : '01 Access'}</strong><Icon name="chevron" size={15} /><strong>{schedule ? '02 Schedule' : ''}</strong><span>{schedule ? '' : '02 Schedule'}</span><Icon name="chevron" size={15} /><span>03 Checkout</span></div>
    <div className="fg-two-column"><div className="fg-panel fg-stack">
      {!schedule ? <>
        <button className={`fg-plan ${draft.accessType === 'GYM' ? 'is-active' : ''}`} aria-pressed={draft.accessType === 'GYM'} onClick={() => update({ accessType: 'GYM', classId: null })}><div className="fg-row"><Icon name="gym" size={28} />{draft.accessType === 'GYM' && <Icon name="check" />}</div><h3>Gym access</h3><p className="fg-muted">Find your rhythm. Access the gym facilities.</p></button>
        {options.data?.has_classes && <button className={`fg-plan ${draft.accessType === 'CLASS' ? 'is-active' : ''}`} aria-pressed={draft.accessType === 'CLASS'} onClick={() => update({ accessType: 'CLASS' })}><div className="fg-row"><Icon name="spark" size={28} />{draft.accessType === 'CLASS' && <Icon name="check" />}</div><h3>Join a class</h3><p className="fg-muted">Move together. Choose an available session.</p></button>}
        <Button onClick={() => navigate(`/gyms/${gymId}/book/schedule`)}>Continue <Icon name="arrow" /></Button>
      </> : <>
        <label className="fg-field">{companionsDate ? 'Visit date · Today (IST)' : 'Select date (IST)'}<input type="date" min={today} value={draft.date} readOnly={!!companionsDate} onChange={e => { if (!companionsDate && e.target.value) update({ date: e.target.value, classId: null, start: '', end: '' }) }} /></label>
        <p className="fg-muted">Booking times are in IST. Choose a start time in the future; availability is checked again before payment.</p>
        {availability.loading ? <Skeleton cards={1} /> : availability.error ? <ErrorState message={availability.error} retry={availability.retry} /> : draft.accessType === 'GYM' ? availability.data?.hours.is_closed ? <Alert>This gym is closed on this date. Choose another day.</Alert> : <>
          <p className="fg-muted">Open {availability.data?.hours.open_time?.slice(0, 5)} – {availability.data?.hours.close_time?.slice(0, 5)}</p>
          <div className="fg-row"><label className="fg-field">Start hour (IST)<select aria-label="Start hour (IST)" value={hours.includes(selectedHour) ? selectedHour : ''} onChange={event => { const start = starts.find(value => value.startsWith(`${event.target.value}:`)) || ''; update({ start, end: oneHourVisitEnd(start) }) }}><option value="">Select hour</option>{hours.map(hour => <option key={hour} value={hour}>{hour}</option>)}</select></label><label className="fg-field">Minutes<select aria-label="Start minutes" disabled={!hours.includes(selectedHour)} value={minutes.includes(selectedMinute) ? selectedMinute : ''} onChange={event => { const start = `${selectedHour}:${event.target.value}`; update({ start, end: oneHourVisitEnd(start) }) }}><option value="">Select minutes</option>{minutes.map(minute => <option key={minute} value={minute}>{minute}</option>)}</select></label></div>
          {starts.includes(draft.start) && endTime && <p role="status">Visit: {draft.start}–{endTime} IST · 1 hour (end time set automatically)</p>}
          {!starts.length && <Alert>No future one-hour visits fit within this day’s opening hours. Choose another date.</Alert>}
          <p className="fg-muted">Your one-time entry QR allows arrival from one hour before your start time (not before opening) until the gym closes on your visit date.</p>
        </> : availability.data?.sessions.length ? <div className="fg-stack"><h3>Choose a session</h3>{availability.data.sessions.map(session => <button key={session.id} disabled={!isBookableSession(session.status, session.available_capacity) || !isFutureBookingStart(session.class_date, session.start_time, now)} aria-pressed={draft.classId === session.id} className={`fg-plan ${draft.classId === session.id ? 'is-active' : ''}`} onClick={() => update({ classId: session.id, memberCount: Math.min(draft.memberCount, session.available_capacity) })}><h3>{session.class_name}</h3><p>{session.start_time.slice(0, 5)} – {session.end_time.slice(0, 5)} IST</p><p className="fg-muted">{session.available_capacity} seats available · {money(session.price_per_person)}</p></button>)}</div> : <EmptyState title="No classes on this date" description="Choose another date or explore gym access." />}
        <div className="fg-row"><div><h3>{companionsDate ? 'Additional people' : 'Members'}</h3><small className="fg-muted">{companionsDate ? 'Friends and family only · You are not counted' : 'You and your workout crew'}</small></div><div className="fg-counter"><Button variant="secondary" aria-label="Remove one member" disabled={draft.memberCount <= 1} onClick={() => update({ memberCount: draft.memberCount - 1 })}>−</Button><output aria-live="polite">{draft.memberCount}</output><Button variant="secondary" aria-label="Add one member" disabled={draft.memberCount >= max} onClick={() => update({ memberCount: draft.memberCount + 1 })}>+</Button></div></div>
        {mutation.error && <Alert>{mutation.error}</Alert>}
        {startTime && !futureStart && <Alert>This start time has passed. Choose a future date and time.</Alert>}
        <fieldset className="fg-stack"><legend>Who will use this booking?</legend><p className="fg-muted">Each person receives their own one-time QR after payment. Enter the actual visitors, not just the purchaser.</p>{Array.from({ length: draft.memberCount }, (_, index) => <label className="fg-field" key={index}>Visitor {index + 1} full name<input required maxLength={150} autoComplete="off" value={visitors[index] || ''} onChange={event => setVisitors(previous => { const next = [...previous]; next[index] = event.target.value; return next })} /></label>)}</fieldset>
        <Button loading={mutation.pending} disabled={!futureStart || availability.loading || !!availability.error || (draft.accessType === 'GYM' ? !starts.includes(draft.start) || !endTime || availability.data?.hours.is_closed : !selected || selected.available_capacity < 1)} onClick={add}>Check availability & add to cart</Button>
        <small className="fg-muted">The gym validates your selection when it is added. Nothing is charged until you confirm payment.</small>
        {!companionsDate && <Link to={`/gyms/${gymId}/book/access`} className="fg-inline-link">Change access type</Link>}
      </>}
    </div><aside className="fg-panel fg-stack"><h3>{companionsDate ? 'Your group visit' : 'Your visit'}</h3><p>{options.data?.gym_name}</p>
      {companionsDate && <div className="fg-success"><strong>You · Covered by membership</strong><p>Your own visit uses My Access and is not added to this paid cart. Only the additional people below are charged.</p></div>}
      <p className="fg-muted">{companionsDate ? 'Day visits' : draft.accessType === 'GYM' ? 'Gym access' : selected?.class_name ?? 'Class access'} · {draft.memberCount} {companionsDate ? 'additional people' : draft.memberCount === 1 ? 'member' : 'members'}</p>
      {price != null ? <><hr className="fg-divider" /><p>{money(price)} × {draft.memberCount} {companionsDate ? 'additional people' : 'members'}</p><div className="fg-total-row"><strong>Estimated total</strong><strong>{money(Number(price) * draft.memberCount)}</strong></div></> : <p className="fg-muted">Choose a session to see pricing.</p>}
      <small className="fg-muted">Final pricing is provided by the gym and confirmed in your cart.</small>
    </aside></div>
  </>
}