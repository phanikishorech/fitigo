import { useState } from 'react'
import { useMutation, useResource } from '../../hooks/useResource'
import { bookingService } from '../../services/bookingService'
import { gymService } from '../../services/gymService'
import { dateLabel, money } from '../../services/client'
import { canReview } from '../../utils/booking'
import { Alert, Badge, Button, ErrorState, Heading, Link, Modal, Skeleton } from '../../components/common/UI'
import Icon from '../../components/common/Icon'

export default function BookingDetailPage({ id, success = false }: { id: number; success?: boolean }) {
  const result = useResource(async () => {
    const booking = await bookingService.detail(id)
    const [gym, visits] = await Promise.all([gymService.details(booking.gym_id), bookingService.visits()])
    return { booking, gym, visit: visits.find(item => item.booking_id === id) }
  }, String(id))
  const mutation = useMutation()
  const [cancel, setCancel] = useState(false)
  if (result.loading) return <Skeleton cards={2} />
  if (result.error) return <ErrorState message={result.error} retry={result.retry} />
  const { booking, gym, visit } = result.data!
  const confirmed = booking.status === 'CONFIRMED'
  const canCancel = ['CONFIRMED', 'PENDING'].includes(booking.status) && !visit?.attendance_status && booking.slot_date >= new Date().toISOString().slice(0, 10)
  const calendar = () => {
    const escape = (text: string) => text.replace(/\\/g, '\\\\').replace(/\n/g, '\\n').replace(/[,;]/g, '\\$&')
    const date = booking.slot_date.replaceAll('-', '')
    const start = (visit?.start_time ?? '09:00:00').replaceAll(':', '')
    const end = (visit?.end_time ?? '10:00:00').replaceAll(':', '')
    const content = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//FitiGo//Bookings//EN', 'BEGIN:VEVENT', `UID:fitigo-booking-${id}`, `DTSTAMP:${new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '')}`, `DTSTART:${date}T${start}`, `DTEND:${date}T${end}`, `SUMMARY:${escape(`Workout at ${gym.gym_name}`)}`, `LOCATION:${escape(gym.location.full_address ?? gym.gym_name)}`, 'END:VEVENT', 'END:VCALENDAR'].join('\r\n')
    const url = URL.createObjectURL(new Blob([content], { type: 'text/calendar;charset=utf-8' }))
    const link = document.createElement('a'); link.href = url; link.download = `fitigo-${id}.ics`; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <div className="fg-narrow">{success && confirmed && <div className="fg-center"><div className="fg-success-mark"><Icon name="check" size={36} /></div><h1>Booking confirmed!</h1><p className="fg-muted">You made time for you. We’ll see you at the gym.</p></div>}<Heading title={success && confirmed ? 'Your workout is booked' : 'Booking details'} subtitle={`Booking #${booking.id}`} /><div className="fg-panel fg-stack"><div className="fg-row"><h2>{gym.gym_name}</h2><Badge tone={confirmed ? 'success' : 'neutral'}>{visit?.attendance_status === 'ATTENDED' ? 'Attended' : booking.status.toLowerCase()}</Badge></div><p className="fg-muted">{gym.location.full_address}</p><p>{visit?.class_name ?? visit?.access_type ?? 'Gym access'}</p><div className="fg-row"><span>Date</span><strong>{dateLabel(booking.slot_date)}</strong></div>{visit && <div className="fg-row"><span>Time</span><strong>{visit.start_time.slice(0, 5)} – {visit.end_time.slice(0, 5)}</strong></div>}<div className="fg-row"><span>Members</span><strong>{booking.quantity}</strong></div><div className="fg-row"><span>Total</span><strong>{money(booking.total_price, booking.currency)}</strong></div><div className="fg-row"><span>Payment status</span><span>{booking.payment?.status ?? 'Not recorded'}</span></div><hr className="fg-divider" /><h3>Before your visit</h3><p className="fg-muted">Keep your booking ID handy. Access is subject to the gym’s entry rules.</p>{gym.rules.map((rule, index) => <p className="fg-muted" key={index}>{rule}</p>)}{confirmed && <Button variant="secondary" onClick={calendar}><Icon name="calendar" />Add to calendar</Button>}{success && <Link to={`/bookings/${id}`} className="fg-button fg-button--primary">View booking</Link>}{visit && canReview(visit) && <Link to={`/reviews/${id}`} className="fg-button fg-button--primary">Rate your visit</Link>}{canCancel && <Button variant="danger" onClick={() => setCancel(true)}>Cancel booking</Button>}<Link to={`/gyms/${booking.gym_id}`} className="fg-inline-link">Book another visit <Icon name="arrow" size={18} /></Link><Link to="/bookings" className="fg-inline-link">View all bookings</Link><Link to="/home" className="fg-inline-link">Back to home</Link></div>{cancel && <Modal title="Cancel this booking?" onClose={() => { if (!mutation.pending) setCancel(false) }}><div className="fg-stack"><p>This action cannot be undone. Refunds depend on the gym’s policy; no refund is promised by this screen.</p>{mutation.error && <Alert>{mutation.error}</Alert>}<Button variant="danger" loading={mutation.pending} onClick={() => mutation.run(async () => { await bookingService.cancel(id); setCancel(false); result.retry() })}>Confirm cancellation</Button><Button variant="secondary" disabled={mutation.pending} onClick={() => setCancel(false)}>Keep my booking</Button></div></Modal>}</div>
}