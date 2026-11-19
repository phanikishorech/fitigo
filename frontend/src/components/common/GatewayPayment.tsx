import { useEffect, useRef, useState } from 'react'
import { paymentService, type PaymentCheckout, type PaymentSource } from '../../services/paymentService'
import { openPayment } from '../../utils/paymentGateway'
import { useMutation } from '../../hooks/useResource'
import { ApiError, dateLabel, money } from '../../services/client'
import { checkoutMessage } from '../../utils/checkoutRecovery'
import { Alert, Button, Link } from './UI'
import Icon from './Icon'
import '../../checkout.css'
import WalletFunding from '../payments/WalletFunding'
import PaymentRecoveryPanel from '../payments/PaymentRecoveryPanel'
import { getSession } from '../../session/store'
import { rememberPaymentReturn, clearPaymentReturn } from '../../utils/paymentReturn'

export default function GatewayPayment({ source, initial, onPaid, onCheckout, onClosed, closedLabel = 'Review current cart', presentation = 'default', matchesSelection = true }: { source?: PaymentSource; initial?: PaymentCheckout; onPaid?: (checkout: PaymentCheckout) => void; onCheckout?: (checkout: PaymentCheckout) => void; onClosed?: () => void; closedLabel?: string; presentation?: 'default' | 'checkout'; matchesSelection?: boolean }) {
  const [checkout, setCheckout] = useState(initial)
  const [recovered, setRecovered] = useState(!!initial)
  const [funding, setFunding] = useState<{ use_wallet: boolean; wallet_amount?: string }>({ use_wallet: false })
  const [fundingReady, setFundingReady] = useState(false)
  const supportsWallet = !!source && source.kind !== 'WALLET_TOPUP'
  const [message, setMessage] = useState('')
  const [confirmCancel, setConfirmCancel] = useState(false)
  const [confirmResume, setConfirmResume] = useState(false)
  const [recoveredMatch, setRecoveredMatch] = useState(matchesSelection)
  const membership = source?.kind === 'MULTI_GYM' || source?.kind === 'SINGLE_GYM' || checkout?.kind === 'MULTI_GYM' || checkout?.kind === 'SINGLE_GYM'
  const [replacementRequired, setReplacementRequired] = useState(false)
  const [replacementAcknowledged, setReplacementAcknowledged] = useState(false)
  const key = useRef(crypto.randomUUID())
  const mutation = useMutation()
  const actionLock = useRef(false)
  const accept = (next: PaymentCheckout) => {
    setCheckout(next)
    setMessage('')
    onCheckout?.(next)
    if (next.status === 'PAID' && checkout?.status !== 'PAID') onPaid?.(next)
  }
  const acceptRef = useRef(accept)
  acceptRef.current = accept
  useEffect(() => {
    if (!checkout || (!['PENDING', 'CREATING', 'FAILED'].includes(checkout.status) && !(checkout.status === 'CANCELLED' && !checkout.replacement_safe))) return
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
  const pay = (replace = false, resumeReserved = false) => run(async () => {
    setConfirmResume(false)
    let next: PaymentCheckout | null
    try {
      if (!checkout && (source?.kind === 'MULTI_GYM' || source?.kind === 'SINGLE_GYM')) {
        const recovered = await paymentService.recoverMembership(source)
        if (recovered.checkout) {
          setRecovered(true)
          accept(recovered.checkout)
          setRecoveredMatch(recovered.matches_selection)
          return
        }
      }
      next = checkout ? await (resumeReserved ? paymentService.resumeMembership(checkout.id) : paymentService.refresh(checkout.id)) : source ? await paymentService.create(
        source.kind === 'CART' ? { ...source, ...funding, confirm_razorpay_replacement: replace } : { ...source, ...funding }, key.current) : null
    } catch (error) {
      if (error instanceof ApiError && error.code === 'RAZORPAY_REPLACEMENT_CONFIRMATION_REQUIRED') {
        setReplacementRequired(true); setReplacementAcknowledged(false); return
      }
      if (!checkout && (source?.kind === 'MULTI_GYM' || source?.kind === 'SINGLE_GYM')) {
        const recovered = await paymentService.recoverMembership(source).catch(() => null)
        if (recovered?.checkout) { setRecovered(true); setRecoveredMatch(recovered.matches_selection); accept(recovered.checkout); return }
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
    if (!checkout && source?.kind === 'MULTI_GYM' && next.order_reference && next.order_reference !== source.order_id) {
      setRecoveredMatch(false)
      return // Another tab's original order must be reviewed, never auto-opened.
    }
    if (!next.can_pay) return
    // Exact current-cart requests were reviewed on this page and checked above.
    // Legacy requests without item IDs still require review before opening.
    if (!checkout && source?.kind === 'CART' && !source.cart_item_ids?.length) return
    const session = getSession()
    if (session.status === 'authenticated') rememberPaymentReturn(session.identity.user.id, next.id)
    const result = await openPayment(next)
    clearPaymentReturn(next.id)
    if (result.type === 'success' || result.type === 'returned') {
      // Only backend capture verification can turn this into success.
      try { accept(await paymentService.verify(next.id, result.type === 'success' ? result.callback : undefined)) }
      catch (error) { setMessage('Checkout returned, but verification was interrupted. Do not pay again; refresh payment status.'); throw error }
    } else {
      setMessage(result.type === 'failed' ? 'Payment failed. Refresh status before retrying this checkout.' : 'Checkout closed or reported an error. Payment is not confirmed. Refresh status before retrying this checkout.')
      const reconciled = await paymentService.refresh(next.id)
      if (!reconciled.can_pay || ['PAID', 'REVIEW_REQUIRED', 'REFUNDED'].includes(reconciled.status)) accept(reconciled)
      else { setCheckout(reconciled); onCheckout?.(reconciled) }
    }
  })
  const cancel = () => run(async () => {
    if (!checkout) return
    setConfirmCancel(false)
    try { accept(await paymentService.cancel(checkout.id)) }
    catch (error) {
      // A lost cancellation response is not proof of failure or safe closure.
      try { accept(await paymentService.status(checkout.id)) } catch { /* Keep the original checkout. */ }
      setMessage('Cancellation could not be confirmed. Check the original payment status; do not start another payment.')
      throw error
    }
  })
  const focused = presentation === 'checkout'
  const statusTitle = checkout?.status === 'REVIEW_REQUIRED' ? 'Payment needs review'
    : checkout?.status === 'PAID' ? 'Payment confirmed'
    : checkout?.payment_blocked_reason === 'BOOKING_EXPIRED' ? 'Payment window expired'
    : checkout?.payment_blocked_reason === 'PAYMENT_PROCESSING' ? 'Confirming your payment'
    : checkout?.can_pay ? 'Awaiting payment' : 'Payment update'
  if (membership && checkout) return <PaymentRecoveryPanel checkout={checkout} matchesSelection={recoveredMatch} previous={!!initial || !recoveredMatch} message={message} error={mutation.error || ''}>
    {!confirmCancel && !confirmResume && (checkout.can_pay || checkout.can_resume_reserved_membership) && !checkout.cancellation_requested && <Button loading={mutation.pending} onClick={() => { if (!recoveredMatch || checkout.can_resume_reserved_membership) setConfirmResume(true); else void pay() }}>{checkout.can_resume_reserved_membership || !recoveredMatch ? 'Resume original membership' : recovered ? 'Resume payment' : 'Continue payment'}</Button>}
    {confirmResume && (checkout.can_pay || checkout.can_resume_reserved_membership) && !checkout.cancellation_requested && <section className="fg-stack" aria-label="Confirm original membership"><p>You are paying for <strong>{checkout.plan_name || 'the original membership'}</strong>, not a different selected plan. Total {money(checkout.total_amount ?? checkout.amount, checkout.currency)}: wallet {money(checkout.wallet_amount || '0', checkout.currency)}, online {money(checkout.gateway_amount ?? checkout.amount, checkout.currency)}. The existing reservation and provider order will be reused.</p><Button loading={mutation.pending} onClick={() => void pay(false, !!checkout.can_resume_reserved_membership)}>Confirm and resume original payment</Button><Button variant="text" disabled={mutation.pending} onClick={() => setConfirmResume(false)}>Not now</Button></section>}
    <Button variant="secondary" loading={mutation.pending} onClick={() => void run(async () => accept(await paymentService.refresh(checkout.id)))}>Refresh payment status</Button>
    {(checkout.can_request_cancel || checkout.can_cancel) && !confirmCancel && <Button variant="text" loading={mutation.pending} onClick={() => setConfirmCancel(true)}>Cancel and change</Button>}
    {confirmCancel && (checkout.can_request_cancel || checkout.can_cancel) && <section className="fg-stack" aria-label="Confirm checkout cancellation"><p>Close any open payment windows. Cancellation requires provider confirmation; wallet funds remain reserved until safe closure. If payment succeeded, that result will be shown instead.</p><Button loading={mutation.pending} onClick={() => void cancel()}>Confirm cancellation</Button><Button variant="text" disabled={mutation.pending} onClick={() => setConfirmCancel(false)}>Keep checkout</Button></section>}
    {checkout.status === 'CANCELLED' && checkout.replacement_safe && checkout.wallet_status !== 'HELD' && checkout.wallet_status !== 'DEBITED' && onClosed && <Button variant="secondary" disabled={mutation.pending} onClick={onClosed}>{closedLabel}</Button>}
  </PaymentRecoveryPanel>
  return <div className={focused ? 'fc-gateway' : 'fg-stack'}>
    {!focused && <>
    <p>Secure {checkout?.provider === 'CASHFREE' ? 'Cashfree' : checkout?.provider === 'RAZORPAY' ? 'Razorpay' : 'payment'} checkout. Your purchase or wallet credit is completed only after FitiGo confirms payment.</p>
    {checkout && <><p><strong>{checkout.mode === 'test' ? 'TEST MODE · No real money' : 'LIVE MODE · Real payment'}</strong></p><p>{money(checkout.amount, checkout.currency)} · {checkout.status.replaceAll('_', ' ').toLowerCase()}</p><small>Checkout: {checkout.id}</small></>}
    {checkout?.payment_expires_at && <p>Booking payment deadline: {new Date(checkout.payment_expires_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST</p>}
    {checkout?.kind === 'CART' && <section className="fg-stack" aria-label="Items in this checkout"><h3>Items in this checkout</h3>
      {checkout.items?.map(item => <div key={item.booking_id}><strong>{item.gym_name}</strong><p>{dateLabel(item.booking_date)} · {item.start_time?.slice(0, 5)} IST · {item.quantity} visitors · {money(item.amount, item.currency)}</p></div>)}
      {!checkout.items?.length && <p>Use the booking links below to review this checkout. Current cart items are not its payment summary.</p>}
      <p><strong>Checkout total: {money(checkout.total_amount ?? checkout.amount, checkout.currency)}</strong></p>
    </section>}
    </>}
    {(message || checkout) && <div className={focused ? `fc-status ${checkout?.status === 'PAID' ? 'fc-status--success' : checkout && !checkout.can_pay ? 'fc-status--attention' : ''}` : undefined} role="status">
      {focused && <Icon name={checkout?.status === 'PAID' ? 'check' : 'clock'} size={19} />}
      <div>{focused && <strong>{statusTitle}</strong>}<p>{message || checkoutMessage(checkout!)}</p></div>
    </div>}
    {supportsWallet && !checkout && <WalletFunding source={source!} disabled={mutation.pending} onChange={(value, ready) => { setFunding(value); setFundingReady(ready) }} />}
    {checkout?.total_amount && <div className="fg-stack"><p>Total purchase: {money(checkout.total_amount, checkout.currency)}</p><p>Wallet: {money(checkout.wallet_amount || '0', checkout.currency)} · {checkout.wallet_status?.toLowerCase()}</p><p>Online payment: {money(checkout.gateway_amount || checkout.amount, checkout.currency)}</p>{checkout.wallet_status === 'HELD' && <small>Wallet funds are reserved, not yet charged. Closing this page does not release them; use Refresh payment status to reconcile.</small>}</div>}
    {checkout?.plan_name && <p>Payment is for: <strong>{checkout.plan_name}</strong></p>}
    {mutation.error && <Alert>{mutation.error}</Alert>}
    {replacementRequired && !checkout && <section className="fg-stack" aria-label="Replace previous checkout">
      <div className="fc-status fc-status--attention" role="status"><div><strong>Start again with your current cart</strong><p>The previous Razorpay order currently has no successful or processing payment. It will be replaced in FitiGo, not cancelled at the gateway. A delayed payment is still possible and would need review.</p></div></div>
      <label className="fg-checkbox"><input type="checkbox" checked={replacementAcknowledged} onChange={event => setReplacementAcknowledged(event.target.checked)} />I have closed old payment windows and no money was deducted. I understand a delayed payment may still need review.</label>
      <Button loading={mutation.pending} disabled={!replacementAcknowledged || (supportsWallet && !fundingReady)} onClick={() => void pay(true)}>Start a fresh checkout</Button>
      <Button variant="text" disabled={mutation.pending} onClick={() => { setReplacementRequired(false); setReplacementAcknowledged(false) }}>Not now</Button>
    </section>}
    {!confirmCancel && !replacementRequired && (!checkout || (checkout.can_pay && !checkout.cancellation_requested)) && <Button loading={mutation.pending} disabled={!checkout && supportsWallet && !fundingReady} onClick={() => void pay()}>{membership && checkout ? 'Resume payment' : focused ? <>{checkout ? 'Continue payment' : 'Pay securely'}<Icon name="arrow" size={18} /></> : checkout ? 'Retry / open payment' : 'Continue to secure payment'}</Button>}
    {checkout && <Button variant="secondary" loading={mutation.pending} onClick={() => void run(async () => accept(await paymentService.refresh(checkout.id)))}>Refresh payment status</Button>}
    {(checkout?.can_request_cancel || checkout?.can_cancel) && !confirmCancel && <Button variant="text" loading={mutation.pending} onClick={() => setConfirmCancel(true)}>{membership ? 'Cancel and change' : 'Cancel unpaid checkout'}</Button>}
    {confirmCancel && <section className="fg-stack" aria-label="Confirm checkout cancellation"><p>Close any open payment windows. We will check the original payment and request cancellation. Your wallet funds and new payment options remain locked until safe closure is confirmed. If payment already succeeded, we will show that result instead.</p><Button loading={mutation.pending} onClick={() => void cancel()}>Confirm cancellation</Button><Button variant="text" disabled={mutation.pending} onClick={() => setConfirmCancel(false)}>Keep checkout</Button></section>}
    {checkout?.status === 'CANCELLED' && checkout.replacement_safe && checkout.wallet_status !== 'HELD' && checkout.wallet_status !== 'DEBITED' && onClosed && <Button variant="secondary" disabled={mutation.pending} onClick={onClosed}>{closedLabel}</Button>}
    {membership && checkout && !checkout.can_request_cancel && !checkout.can_cancel && !['PAID', 'REFUNDED', 'CANCELLED'].includes(checkout.status) && <p>Check the original payment status before changing plans. If the provider cannot safely close this checkout, contact support from Payment history. Do not pay another order.</p>}
    {focused && checkout && <details className="fc-details"><summary>Payment details <Icon name="down" size={15} /></summary><dl><dt>Checkout reference</dt><dd>{checkout.id}</dd><dt>Provider</dt><dd>{checkout.provider} · {checkout.mode === 'test' ? 'Test mode' : 'Live mode'}</dd><dt>Status</dt><dd>{checkout.status.replaceAll('_', ' ').toLowerCase()}</dd>{checkout.payment_expires_at && <><dt>Original payment deadline</dt><dd>{new Date(checkout.payment_expires_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' })} IST</dd></>}{checkout.failure_code && <><dt>Review reason</dt><dd>{checkout.failure_code.replaceAll('_', ' ').toLowerCase()}</dd></>}</dl></details>}
    <div className={focused ? 'fc-payment-links' : 'fg-stack'}>
    {checkout?.booking_ids.map(id => <Link key={id} to={`/bookings/${id}`} className="fg-inline-link">View booking #{id}</Link>)}
    {checkout?.membership_id && <Link to={`/membership/${checkout.membership_id}`} className="fg-inline-link">View membership</Link>}
    <Link to="/profile/payments" className="fg-inline-link">View payment history</Link>
    </div>
  </div>
}