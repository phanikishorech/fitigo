import { useEffect, useRef, useState } from 'react'
import { paymentService, type PaymentCheckout, type PaymentSource } from '../../services/paymentService'
import { openPayment } from '../../utils/paymentGateway'
import { useMutation } from '../../hooks/useResource'
import { money } from '../../services/client'
import { Alert, Button, Link } from './UI'

export default function GatewayPayment({ source, initial, onPaid }: { source?: PaymentSource; initial?: PaymentCheckout; onPaid?: (checkout: PaymentCheckout) => void }) {
  const [checkout, setCheckout] = useState(initial)
  const [message, setMessage] = useState('')
  const key = useRef(crypto.randomUUID())
  const mutation = useMutation()
  const accept = (next: PaymentCheckout) => {
    setCheckout(next)
    if (next.status === 'PAID') { setMessage('Payment confirmed by FitiGo.'); onPaid?.(next) }
    else if (next.status === 'REVIEW_REQUIRED') setMessage('Payment received, but this purchase could not be fulfilled. Do not pay again. Contact support with this checkout ID for reconciliation/refund.')
    else if (next.status === 'PENDING' || next.status === 'CREATING') setMessage('Payment is not confirmed yet. Refresh status before retrying. Your booking/membership is not active.')
    else if (next.status === 'FAILED') setMessage('Payment failed. You can retry this same checkout without creating another purchase.')
    else setMessage(`Payment status: ${next.status.toLowerCase()}.`)
  }
  useEffect(() => {
    if (!checkout || !['PENDING', 'CREATING'].includes(checkout.status)) return
    let active = true
    let checking = false
    const timer = window.setInterval(() => {
      if (checking || mutation.pending) return
      checking = true
      void paymentService.refresh(checkout.id).then(next => { if (active && next.status !== checkout.status) accept(next) }).catch(() => {}).finally(() => { checking = false })
    }, 15000)
    return () => { active = false; clearInterval(timer) }
  }, [checkout?.id, checkout?.status, mutation.pending])
  const pay = () => mutation.run(async () => {
    const next = checkout ? await paymentService.refresh(checkout.id) : source ? await paymentService.create(source, key.current) : null
    if (!next) throw new Error('Choose a purchase first.')
    accept(next)
    if (!next.can_pay) return
    const result = await openPayment(next)
    if (result.type === 'success' || result.type === 'returned') {
      // Only backend capture verification can turn this into success.
      try { accept(await paymentService.verify(next.id, result.type === 'success' ? result.callback : undefined)) }
      catch (error) { setMessage('Checkout returned, but verification was interrupted. Do not pay again; refresh payment status.'); throw error }
    } else {
      setMessage(result.type === 'failed' ? 'Payment failed. Refresh status before retrying this checkout.' : 'Checkout closed or reported an error. Payment is not confirmed. Refresh status before retrying this checkout.')
      const reconciled = await paymentService.refresh(next.id)
      if (['PAID', 'REVIEW_REQUIRED', 'REFUNDED'].includes(reconciled.status)) accept(reconciled)
      else setCheckout(reconciled)
    }
  })
  return <div className="fg-stack">
    <p>Secure {checkout?.provider === 'CASHFREE' ? 'Cashfree' : checkout?.provider === 'RAZORPAY' ? 'Razorpay' : 'payment'} checkout. Access is granted only after FitiGo confirms payment.</p>
    {checkout && <><p><strong>{checkout.mode === 'test' ? 'TEST MODE · No real money' : 'LIVE MODE · Real payment'}</strong></p><p>{money(checkout.amount, checkout.currency)} · {checkout.status.replaceAll('_', ' ').toLowerCase()}</p><small>Checkout: {checkout.id}</small></>}
    {message && <p role="status">{message}</p>}
    {mutation.error && <Alert>{mutation.error}</Alert>}
    {(!checkout || checkout.can_pay) && <Button loading={mutation.pending} onClick={() => void pay()}>{checkout ? 'Retry / open payment' : 'Continue to secure payment'}</Button>}
    {checkout && <Button variant="secondary" loading={mutation.pending} onClick={() => void mutation.run(async () => accept(await paymentService.refresh(checkout.id)))}>Refresh payment status</Button>}
    {checkout && ['CREATED', 'CREATING', 'PENDING', 'FAILED'].includes(checkout.status) && <Button variant="text" loading={mutation.pending} onClick={() => void mutation.run(async () => accept(await paymentService.cancel(checkout.id)))}>Cancel unpaid checkout</Button>}
    {checkout?.booking_ids.map(id => <Link key={id} to={`/bookings/${id}`} className="fg-inline-link">View booking #{id}</Link>)}
    {checkout?.membership_id && <Link to={`/membership/${checkout.membership_id}`} className="fg-inline-link">View membership</Link>}
    <Link to="/checkout" className="fg-inline-link">Review checkout / recent payments</Link>
  </div>
}