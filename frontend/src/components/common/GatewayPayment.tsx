import { useEffect, useRef, useState } from 'react'
import { paymentService, type PaymentCheckout, type PaymentSource } from '../../services/paymentService'
import { openPayment } from '../../utils/paymentGateway'
import { useMutation } from '../../hooks/useResource'
import { ApiError, dateLabel, money } from '../../services/client'
import { checkoutMessage } from '../../utils/checkoutRecovery'
import { Alert, Button, Link } from './UI'
import Icon from './Icon'
import '../../checkout.css'

export default function GatewayPayment({ source, initial, onPaid, onCheckout, onClosed, presentation = 'default' }: { source?: PaymentSource; initial?: PaymentCheckout; onPaid?: (checkout: PaymentCheckout) => void; onCheckout?: (checkout: PaymentCheckout) => void; onClosed?: () => void; presentation?: 'default' | 'checkout' }) {
  const [checkout, setCheckout] = useState(initial)
  const [message, setMessage] = useState('')
  const [replacementRequired, setReplacementRequired] = useState(false)
  const [replacementAcknowledged, setReplacementAcknowledged] = useState(false)
  const key = useRef(crypto.randomUUID())
  const mutation = useMutation()
  const actionLock = useRef(false)
  const accept = (next: PaymentCheckout) => {
    setCheckout(next)
    setMessage(checkoutMessage(next))
    onCheckout?.(next)
    if (next.status === 'PAID' && checkout?.status !== 'PAID') onPaid?.(next)
  }
  const acceptRef = useRef(accept)
  acceptRef.current = accept
  useEffect(() => {
    if (!checkout || !['PENDING', 'CREATING', 'FAILED'].includes(checkout.status)) return
    let active = true
    let checking = false
    const timer = window.setInterval(() => {
      if (checking || mutation.pending || actionLock.current) return
      checking = true
      void paymentService.refresh(checkout.id).then(next => { if (active && !actionLock.current) acceptRef.current(next) }).catch(() => {}).finally(() => { checking = false })
    }, 15000)
    return () => { active = false; clearInterval(timer) }
  }, [checkout?.id, checkout?.status, mutation.pending])
  const run = (action: () => Promise<void>) => mutation.run(async () => {
    actionLock.current = true
    try { await action() } finally { actionLock.current = false }
  })
  const pay = (replace = false) => run(async () => {
    let next: PaymentCheckout | null
    try {
      next = checkout ? await paymentService.refresh(checkout.id) : source ? await paymentService.create(
        source.kind === 'CART' ? { ...source, confirm_razorpay_replacement: replace } : source, key.current) : null
    } catch (error) {
      if (error instanceof ApiError && error.code === 'RAZORPAY_REPLACEMENT_CONFIRMATION_REQUIRED') {
        setReplacementRequired(true); setReplacementAcknowledged(false); return
      }
      throw error
    }
    if (!next) throw new Error('Choose a purchase first.')
    if (source?.kind === 'CART' && source.cart_item_ids &&
        (next.cart_item_ids?.length !== source.cart_item_ids.length ||
          !source.cart_item_ids.every(id => next.cart_item_ids?.includes(id)))) {
      throw new Error('The returned checkout does not match your current cart. Reload the cart; no payment was opened.')
    }
    accept(next)
    setReplacementRequired(false); setReplacementAcknowledged(false)
    if (!next.can_pay) return
    // Exact current-cart requests were reviewed on this page and checked above.
    // Legacy requests without item IDs still require review before opening.
    if (!checkout && source?.kind === 'CART' && !source.cart_item_ids?.length) return
    const result = await openPayment(next)
    if (result.type === 'success' || result.type === 'returned') {
      // Only backend capture verification can turn this into success.
      try { accept(await paymentService.verify(next.id, result.type === 'success' ? result.callback : undefined)) }
      catch (error) { setMessage('Checkout returned, but verification was interrupted. Do not pay again; refresh payment status.'); throw error }
    } else {
      setMessage(result.type === 'failed' ? 'Payment failed. Refresh status before retrying this checkout.' : 'Checkout closed or reported an error. Payment is not confirmed. Refresh status before retrying this checkout.')
      const reconciled = await paymentService.refresh(next.id)
      if (!reconciled.can_pay || ['PAID', 'REVIEW_REQUIRED', 'REFUNDED'].includes(reconciled.status)) accept(reconciled)
      else setCheckout(reconciled)
    }
  })
  const focused = presentation === 'checkout'
  const statusTitle = checkout?.status === 'REVIEW_REQUIRED' ? 'Payment needs review'
    : checkout?.status === 'PAID' ? 'Payment confirmed'
    : checkout?.payment_blocked_reason === 'BOOKING_EXPIRED' ? 'Payment window expired'
    : checkout?.payment_blocked_reason === 'PAYMENT_PROCESSING' ? 'Confirming your payment'
    : checkout?.can_pay ? 'Awaiting payment' : 'Payment update'
  return <div className={focused ? 'fc-gateway' : 'fg-stack'}>
    {!focused && <>
    <p>Secure {checkout?.provider === 'CASHFREE' ? 'Cashfree' : checkout?.provider === 'RAZORPAY' ? 'Razorpay' : 'payment'} checkout. Your purchase or wallet credit is completed only after FitiGo confirms payment.</p>
    {checkout && <><p><strong>{checkout.mode === 'test' ? 'TEST MODE · No real money' : 'LIVE MODE · Real payment'}</strong></p><p>{money(checkout.amount, checkout.currency)} · {checkout.status.replaceAll('_', ' ').toLowerCase()}</p><small>Checkout: {checkout.id}</small></>}
    {checkout?.payment_expires_at && <p>Booking payment deadline: {new Date(checkout.payment_expires_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST</p>}
    {checkout?.kind === 'CART' && <section className="fg-stack" aria-label="Items in this checkout"><h3>Items in this checkout</h3>
      {checkout.items?.map(item => <div key={item.booking_id}><strong>{item.gym_name}</strong><p>{dateLabel(item.booking_date)} · {item.start_time?.slice(0, 5)} IST · {item.quantity} visitors · {money(item.amount, item.currency)}</p></div>)}
      {!checkout.items?.length && <p>Use the booking links below to review this checkout. Current cart items are not its payment summary.</p>}
      <p><strong>Checkout total: {money(checkout.amount, checkout.currency)}</strong></p>
    </section>}
    </>}
    {(message || checkout) && <div className={focused ? `fc-status ${checkout?.status === 'PAID' ? 'fc-status--success' : checkout && !checkout.can_pay ? 'fc-status--attention' : ''}` : undefined} role="status">
      {focused && <Icon name={checkout?.status === 'PAID' ? 'check' : 'clock'} size={19} />}
      <div>{focused && <strong>{statusTitle}</strong>}<p>{message || checkoutMessage(checkout!)}</p></div>
    </div>}
    {mutation.error && <Alert>{mutation.error}</Alert>}
    {replacementRequired && !checkout && <section className="fg-stack" aria-label="Replace previous checkout">
      <div className="fc-status fc-status--attention" role="status"><div><strong>Start again with your current cart</strong><p>The previous Razorpay order currently has no successful or processing payment. It will be replaced in FitiGo, not cancelled at the gateway. A delayed payment is still possible and would need review.</p></div></div>
      <label className="fg-checkbox"><input type="checkbox" checked={replacementAcknowledged} onChange={event => setReplacementAcknowledged(event.target.checked)} />I have closed old payment windows and no money was deducted. I understand a delayed payment may still need review.</label>
      <Button loading={mutation.pending} disabled={!replacementAcknowledged} onClick={() => void pay(true)}>Start a fresh checkout</Button>
      <Button variant="text" disabled={mutation.pending} onClick={() => { setReplacementRequired(false); setReplacementAcknowledged(false) }}>Not now</Button>
    </section>}
    {!replacementRequired && (!checkout || checkout.can_pay) && <Button loading={mutation.pending} onClick={() => void pay()}>{focused ? <>{checkout ? 'Continue payment' : 'Pay securely'}<Icon name="arrow" size={18} /></> : checkout ? 'Retry / open payment' : 'Continue to secure payment'}</Button>}
    {checkout && <Button variant="secondary" loading={mutation.pending} onClick={() => void run(async () => accept(await paymentService.refresh(checkout.id)))}>Refresh payment status</Button>}
    {checkout?.can_cancel && <Button variant="text" loading={mutation.pending} onClick={() => void run(async () => accept(await paymentService.cancel(checkout.id)))}>Cancel unpaid checkout</Button>}
    {checkout?.status === 'CANCELLED' && checkout.replacement_safe && onClosed && <Button variant="secondary" onClick={onClosed}>Review current cart</Button>}
    {focused && checkout && <details className="fc-details"><summary>Payment details <Icon name="down" size={15} /></summary><dl><dt>Checkout reference</dt><dd>{checkout.id}</dd><dt>Provider</dt><dd>{checkout.provider} · {checkout.mode === 'test' ? 'Test mode' : 'Live mode'}</dd><dt>Status</dt><dd>{checkout.status.replaceAll('_', ' ').toLowerCase()}</dd>{checkout.payment_expires_at && <><dt>Original payment deadline</dt><dd>{new Date(checkout.payment_expires_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' })} IST</dd></>}{checkout.failure_code && <><dt>Review reason</dt><dd>{checkout.failure_code.replaceAll('_', ' ').toLowerCase()}</dd></>}</dl></details>}
    <div className={focused ? 'fc-payment-links' : 'fg-stack'}>
    {checkout?.booking_ids.map(id => <Link key={id} to={`/bookings/${id}`} className="fg-inline-link">View booking #{id}</Link>)}
    {checkout?.membership_id && <Link to={`/membership/${checkout.membership_id}`} className="fg-inline-link">View membership</Link>}
    <Link to="/profile/payments" className="fg-inline-link">View payment history</Link>
    </div>
  </div>
}