import { useState, type ReactNode } from 'react'
import type { PaymentCheckout } from '../../services/paymentService'
import { money } from '../../services/client'
import { paymentRecoverySummary, paymentSupportDraft } from '../../utils/paymentRecovery'
import SupportContact from '../common/SupportContact'
import { Alert, Button, Link } from '../common/UI'
import './paymentRecovery.css'

export default function PaymentRecoveryPanel({ checkout, matchesSelection, previous, message, error, children }: {
  checkout: PaymentCheckout; matchesSelection: boolean; previous: boolean; message: string; error: string; children: ReactNode
}) {
  const [support, setSupport] = useState(false)
  const summary = paymentRecoverySummary(checkout)
  return <section className="pr-panel" aria-label="Membership payment recovery">
    <header className="pr-header"><div><span className="pr-eyebrow">{previous ? 'Previous membership checkout' : 'Membership payment'}</span><h3>{checkout.plan_name || 'Membership purchase'}</h3></div><span className="pr-mode">{checkout.mode === 'test' ? 'TEST MODE · No real money' : 'LIVE MODE · Real payment'}</span></header>
    {!matchesSelection && <p className="pr-context">This payment belongs to a different selection. Resolving it will not change your selected plan or its price.</p>}
    <div className="pr-status" role="status"><strong>{summary.title}</strong><p>{message || summary.message}</p></div>
    <dl className="pr-breakdown" aria-label="Original payment breakdown">
      <div><dt>Total purchase</dt><dd>{money(checkout.total_amount ?? checkout.amount, checkout.currency)}</dd></div>
      <div><dt>Wallet · {checkout.wallet_status === 'HELD' ? 'reserved' : checkout.wallet_status === 'DEBITED' ? 'charged' : checkout.wallet_status === 'RELEASED' ? 'released' : 'not used'}</dt><dd>{money(checkout.wallet_amount || '0', checkout.currency)}</dd></div>
      <div><dt>Online payment</dt><dd>{money(checkout.gateway_amount ?? checkout.amount, checkout.currency)}</dd></div>
    </dl>
    {error && <Alert>{error}</Alert>}
    <div className="pr-actions">{children}{checkout.can_contact_support && <Button variant="secondary" onClick={() => setSupport(value => !value)}>{support ? 'Hide support' : 'Contact support'}</Button>}</div>
    <details className="pr-details"><summary>Payment details</summary><dl>
      <dt>Checkout reference</dt><dd>{checkout.id}</dd>
      <dt>Order reference</dt><dd>{checkout.order_reference || 'Not available'}</dd>
      <dt>Provider order</dt><dd>{checkout.gateway_order_id || 'Not available'}</dd>
      <dt>Payment reference</dt><dd>{checkout.payment_reference || 'Not available'}</dd>
      <dt>Provider</dt><dd>{checkout.provider}</dd>
      <dt>Recorded checkout status</dt><dd>{checkout.status.replaceAll('_', ' ').toLowerCase()}</dd>
      {checkout.wallet_hold_expires_at && <><dt>Wallet reservation deadline (not provider closure)</dt><dd>{new Date(checkout.wallet_hold_expires_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST</dd></>}
      {checkout.failure_code && <><dt>Review reason</dt><dd>{checkout.failure_code.replaceAll('_', ' ').toLowerCase()}</dd></>}
    </dl></details>
    {support && <section className="pr-support" aria-label="Payment support"><p>A support request does not cancel payment or release wallet funds.</p><SupportContact prefill={paymentSupportDraft(checkout)} /></section>}
    <Link to="/profile/payments" className="fg-inline-link">View payment history</Link>
    {checkout.membership_id && <Link to={`/membership/${checkout.membership_id}`} className="fg-inline-link">View membership</Link>}
  </section>
}