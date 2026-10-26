import { useEffect, useRef, useState } from 'react'
import AccessQr from '../../components/AccessQr'
import { Alert, Button, Modal, Skeleton } from '../../components/common/UI'
import { useMutation } from '../../hooks/useResource'
import { bookingService, type Booking, type BookingQr } from '../../services/bookingService'
import { istDateTime } from '../../utils/membership'
import { dateLabel } from '../../services/client'
import Icon from '../../components/common/Icon'
import { hasBookingCheckin, reconcileBookingQr } from '../../utils/bookingQr'
import GatewayPayment from '../../components/common/GatewayPayment'

export default function BookingAccess({ booking, gymName, refresh }: { booking: Booking; gymName: string; refresh: () => void }) {
  const [open, setOpen] = useState(false)
  const [names, setNames] = useState<string[]>([])
  const mutation = useMutation()
  const access = booking.access
  if (!access) return <Alert>Refresh this booking to check QR availability.</Alert>
  const checkedIn = access.status === 'BOOKING_ALREADY_USED' && access.passes.length > 0 && access.passes.every(hasBookingCheckin)
  return <section className="fg-stack" aria-label="Booking access">
    {booking.status === 'PENDING_PAYMENT' && booking.payment?.provider === 'RAZORPAY' && <GatewayPayment source={{ kind: 'BOOKING', booking_id: booking.id }} onPaid={refresh} />}
    <div className="fg-row"><h3>Booking access</h3><strong>{checkedIn ? 'Your access is approved' : access.message}</strong></div>
    {access.valid_from && access.expires_at && <p>Entry allowed: {istDateTime(access.valid_from)} – {istDateTime(access.expires_at)} · One entry only</p>}
    {booking.visitor_names && <p>Visitors: {booking.visitor_names.join(', ')}</p>}
    {access.passes.filter(pass => pass.checked_in_at).map(pass => <p key={pass.qr_id}>{pass.visitor_name} · Checked in {istDateTime(pass.checked_in_at!)}</p>)}
    {access.can_set_visitors && <form className="fg-stack" onSubmit={event => {
      event.preventDefault()
      void mutation.run(async () => { await bookingService.visitors(booking.id, Array.from({ length: booking.quantity }, (_, i) => (names[i] || '').trim())); refresh() })
    }}><p>This booking has no visitor identities yet. Add the actual visitors once; names cannot be changed after assignment.</p>
      {Array.from({ length: booking.quantity }, (_, i) => <label className="fg-field" key={i}>Visitor {i + 1} full name<input required maxLength={150} value={names[i] || ''} onChange={event => setNames(previous => { const next = [...previous]; next[i] = event.target.value; return next })} /></label>)}
      <Button type="submit" loading={mutation.pending}>Save visitors</Button>{mutation.error && <Alert>{mutation.error}</Alert>}
    </form>}
    {access.qr_available && <Button onClick={() => setOpen(true)}>Show Booking QR</Button>}
    {open && <Modal title="Booking QR" onClose={() => { setOpen(false); refresh() }}><BookingQrView bookingId={booking.id} gymName={gymName} date={booking.slot_date} /></Modal>}
  </section>
}

function BookingQrView({ bookingId, gymName, date }: { bookingId: number; gymName: string; date: string }) {
  const [qr, setQr] = useState<BookingQr | null>(null)
  const [error, setError] = useState('')
  const [version, setVersion] = useState(0)
  const [clock, setClock] = useState(Date.now())
  const issuance = useRef<{ key: string; promise: Promise<BookingQr> } | null>(null)
  useEffect(() => {
    let active = true
    let displayed: BookingQr | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    const hide = () => { active = false; setQr(null); setError('Recheck booking access before displaying your QR.'); if (timer) clearTimeout(timer) }
    const visibility = () => { if (document.hidden) hide() }
    const poll = async () => {
      try {
        const current = await bookingService.detail(bookingId)
        if (!active) return
        const next = displayed ? reconcileBookingQr(displayed, current.access) : null
        if (!next) { setQr(null); setError(current.access.message); return }
        displayed = next
        setQr(next)
        setError('')
        if (!next.passes.every(hasBookingCheckin)) timer = setTimeout(() => void poll(), 4000)
      } catch (e) { if (active) { setQr(null); setError(e instanceof Error ? e.message : 'Unable to verify booking access.') } }
    }
    setQr(null); setError('')
    // Share only this mount's in-flight request across StrictMode effect replay.
    // Never persist raw QR tokens in storage or a global cache.
    const key = `${bookingId}:${version}`
    if (issuance.current?.key !== key) issuance.current = { key, promise: bookingService.qr(bookingId) }
    void issuance.current.promise.then(data => {
      if (active && !document.hidden) { displayed = data; setQr(data); timer = setTimeout(() => void poll(), 4000) }
    }).catch(e => { if (active) setError(e instanceof Error ? e.message : 'Unable to load QR.') })
    const tick = setInterval(() => setClock(Date.now()), 1000)
    document.addEventListener('visibilitychange', visibility)
    window.addEventListener('pagehide', hide)
    return () => { active = false; if (timer) clearTimeout(timer); clearInterval(tick); document.removeEventListener('visibilitychange', visibility); window.removeEventListener('pagehide', hide) }
  }, [bookingId, version])
  return <div className="fg-stack"><h3>{gymName}</h3><p>{dateLabel(date)}</p>
    {error ? <><Alert>{error}</Alert><Button onClick={() => setVersion(v => v + 1)}>Refresh booking access</Button></> : !qr ? <Skeleton cards={1} /> : <>
      {!qr.passes.every(hasBookingCheckin) && <p>Show the visitor’s QR to gym staff. Each QR admits only that named visitor once. Staff must verify the visitor’s identity.</p>}
      {qr.passes.map(pass => <section className="fg-panel fg-stack fg-center fg-booking-qr-card" key={pass.qr_id}><h3>{pass.visitor_name}</h3>
        {hasBookingCheckin(pass) ? <div className="fg-success fg-stack fg-center" role="status" aria-live="polite"><span className="fg-success-mark"><Icon name="check" size={36} /></span><h2>Your access is approved</h2><p>Check-in successful. Enjoy your workout!</p><p>Checked in {istDateTime(pass.checked_in_at!)}</p></div> : pass.qr_token && Date.parse(pass.expires_at) > clock ? <><AccessQr token={pass.qr_token} label={`Booking QR for ${pass.visitor_name}`} /><p>Valid from {istDateTime(pass.valid_from)}</p><p>Valid until {istDateTime(pass.expires_at)}</p></> : <strong>{pass.status === 'USED' ? 'This booking access has already been used.' : 'QR unavailable or expired'}</strong>}
      </section>)}
    </>}
  </div>
}