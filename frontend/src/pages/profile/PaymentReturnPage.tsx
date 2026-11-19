import { useEffect, useRef, useState } from 'react'
import { paymentService, type PaymentCheckout } from '../../services/paymentService'
import { money } from '../../services/client'
import { Alert, Button, Heading, Link } from '../../components/common/UI'
import { checkoutMessage } from '../../utils/checkoutRecovery'
import { clearPaymentReturn, paymentReturnReference } from '../../utils/paymentReturn'
import { navigate } from '../../router'

export default function PaymentReturnPage({ checkoutId }: { checkoutId: string | null }) {
  const [checkout, setCheckout] = useState<PaymentCheckout | null>(null)
  const [error, setError] = useState('')
  const [checking, setChecking] = useState(false)
  const [retry, setRetry] = useState(0)
  const inFlight = useRef(false)
  useEffect(() => {
    if (!checkoutId) return
    if (!paymentReturnReference(window.location.search).requested) {
      navigate(`/checkout?payment_checkout_id=${encodeURIComponent(checkoutId)}`, true)
      return
    }
    let active = true, attempts = 0
    let timer: ReturnType<typeof setTimeout> | undefined
    const check = async () => {
      if (!active) return
      if (inFlight.current) { timer = setTimeout(check, 100); return }
      inFlight.current = true; setChecking(true); setError('')
      try {
        // Verify is reconciliation only; unlike refresh it cannot start an order
        // or request cancellation. Never trust a URL/SDK success flag.
        const next = await paymentService.verify(checkoutId)
        if (!active) return
        setCheckout(next)
        if (['PAID', 'REFUNDED', 'REVIEW_REQUIRED', 'CANCELLED'].includes(next.status)) clearPaymentReturn(checkoutId)
        if (['PENDING', 'CREATING', 'CREATED', 'FAILED'].includes(next.status) && ++attempts < 12) timer = setTimeout(check, 5000)
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : 'Unable to verify payment. Please check again.')
      } finally {
        inFlight.current = false
        if (active) setChecking(false)
      }
    }
    void check()
    return () => { active = false; if (timer) clearTimeout(timer) }
  }, [checkoutId, retry])
  if (!checkoutId) return <div className="fg-narrow fg-stack"><Heading title="Payment reference unavailable" /><Alert>This return link has a missing, invalid or conflicting payment reference. No payment result can be inferred from it.</Alert><Link to="/profile/payments">View your payment history</Link></div>
  const paid = checkout?.status === 'PAID'
  const title = paid ? 'Payment confirmed' : checkout?.status === 'REVIEW_REQUIRED' ? 'Payment needs review' : checkout?.status === 'REFUNDED' ? 'Payment refunded' : checkout?.status === 'CANCELLED' ? 'Checkout closed' : 'Checking your payment'
  return <div className="fg-narrow fg-stack" aria-label="Payment result"><Heading title={title} subtitle="Payment status verified by FitiGo, not by the browser redirect." />
    <section className="fg-panel fg-stack" aria-live="polite">
      {!checkout && !error && <p role="status">Checking the original payment with the provider…</p>}
      {error && <Alert>{error} Do not pay again until the original payment is resolved.</Alert>}
      {checkout && <>
        <strong>{checkout.mode === 'test' ? 'TEST MODE · No real money' : 'LIVE MODE · Real payment'}</strong>
        <h2>{checkout.plan_name || (checkout.kind === 'WALLET_TOPUP' ? 'Wallet recharge' : 'Your purchase')}</h2>
        <p>{checkoutMessage(checkout)}</p>
        <dl><dt>Total purchase</dt><dd>{money(checkout.total_amount ?? checkout.amount, checkout.currency)}</dd><dt>Wallet contribution</dt><dd>{money(checkout.wallet_amount || '0', checkout.currency)}</dd><dt>Online payment</dt><dd>{money(checkout.gateway_amount ?? checkout.amount, checkout.currency)}</dd></dl>
        {paid && checkout.membership_id && <><p>Your membership has been activated.</p><Link to={`/membership/${checkout.membership_id}`} className="fg-button fg-button--primary">View your membership</Link></>}
        {paid && checkout.booking_ids.map(id => <Link key={id} to={`/bookings/${id}`} className="fg-button fg-button--primary">View booking #{id}</Link>)}
        {paid && checkout.kind === 'WALLET_TOPUP' && <Link to="/wallet" className="fg-button fg-button--primary">View wallet</Link>}
        {!paid && checkout.order_reference && <Link to={`/membership/checkout?orderId=${encodeURIComponent(checkout.order_reference)}`}>Return to the original membership checkout</Link>}
        <details><summary>Payment details</summary><p style={{ overflowWrap: 'anywhere' }}>Checkout: {checkout.id}</p><p>Payment reference: {checkout.payment_reference || 'Not available yet'}</p><p>Provider: {checkout.provider}</p></details>
      </>}
      <Button variant="secondary" loading={checking} onClick={() => setRetry(value => value + 1)}>Refresh payment status</Button>
      <Link to="/profile/payments">View payment history</Link>
    </section>
  </div>
}