import { useState } from 'react'
import { useMutation, useResource } from '../../hooks/useResource'
import { bookingService } from '../../services/bookingService'
import { walletService, profileService } from '../../services/accountService'
import { dateLabel, money } from '../../services/client'
import { amountInMinorUnits } from '../../utils/booking'
import { navigate } from '../../router'
import { Alert, Button, EmptyState, ErrorState, Heading, Link, Modal, Skeleton } from '../../components/common/UI'
import Icon from '../../components/common/Icon'
import GatewayPayment from '../../components/common/GatewayPayment'
import { paymentService, type PaymentCheckout } from '../../services/paymentService'
import { pendingCartCheckout } from '../../utils/checkoutRecovery'
import CheckoutVisitCard, { type CheckoutVisit } from '../../components/payments/CheckoutVisitCard'
import '../../checkout.css'

export default function CartPage({ checkout = false }: { checkout?: boolean }) {
  const result = useResource(async () => {
    const cart = await bookingService.cart()
    const gateway = checkout ? await paymentService.config() : null
    const payments = gateway?.enabled ? await paymentService.recent() : []
    const wallet = checkout && !gateway?.enabled && !gateway?.gateway_required ? await walletService.balance() : null
    const user = checkout ? await profileService.me() : null
    return { cart, wallet, user, gateway, payments }
  }, String(checkout))
  const [confirm, setConfirm] = useState(false)
  const [selectedCheckout, setSelectedCheckout] = useState<PaymentCheckout>()
  const mutation = useMutation()
  if (result.loading) return <Skeleton cards={2} />
  if (result.error) return <ErrorState message={result.error} retry={result.retry} />
  const { cart, wallet, user, gateway, payments } = result.data!
  // New active cart items are an explicit new purchase, not an invitation to
  // silently resume an unrelated historical order.
  const previous = cart.length ? undefined : pendingCartCheckout(payments)
  const currentCheckout = selectedCheckout ?? previous
  const newItems = cart.filter(item => !currentCheckout?.cart_item_ids?.includes(item.id))
  const totalMinor = cart.reduce((sum, item) => sum + amountInMinorUnits(item.total_price), 0)
  const currency = cart[0]?.currency ?? wallet?.currency ?? 'INR'
  const sufficient = wallet && wallet.currency === currency && amountInMinorUnits(wallet.balance) >= totalMinor
  const pay = () => mutation.run(async () => {
    const balance = await walletService.balance()
    if (balance.currency !== currency || amountInMinorUnits(balance.balance) < totalMinor) { setConfirm(false); throw new Error('Your wallet balance changed. Refresh this page to review your payment.') }
    let paid
    try { paid = await bookingService.pay() }
    catch (error) { setConfirm(false); throw error }
    setConfirm(false)
    const id = paid.booking_ids?.[0]
    if (id) navigate(`/booking/${id}/success`)
    else navigate('/bookings')
  })
  if (checkout && gateway?.gateway_required && !gateway.enabled) return <><Heading title="Payments unavailable" /><Alert>The selected payment provider is not configured for this mode. No payment has been taken. Contact the administrator or retry later.</Alert><Link to="/cart">Return to cart</Link></>
  if (checkout && gateway?.enabled) {
    const provider = (currentCheckout?.provider ?? gateway.provider) === 'CASHFREE' ? 'Cashfree' : 'Razorpay'
    const testMode = (currentCheckout?.mode ?? gateway.mode) === 'test'
    const visits: CheckoutVisit[] = currentCheckout ? (currentCheckout.items ?? []).map(item => ({ id: item.booking_id, name: item.gym_name,
      date: item.booking_date, start: item.start_time, quantity: item.quantity, amount: item.amount, currency: item.currency }))
      : cart.map(item => ({ id: item.id, name: item.gym_name || 'Gym visit', date: item.booking_date, start: item.start_time || item.preferred_start_time,
        end: item.end_time || item.preferred_end_time, quantity: item.member_count, amount: item.total_price, currency: item.currency, label: item.class_name || 'GYM ACCESS' }))
    const total = currentCheckout ? money(currentCheckout.total_amount ?? currentCheckout.amount, currentCheckout.currency) : money((totalMinor / 100).toFixed(2), currency)
    const history = payments.filter(payment => payment.id !== currentCheckout?.id)
    const hasPurchase = !!cart.length || !!currentCheckout
    return <div className="fc-checkout">
      <Link to="/cart" className="fc-back"><Icon name="back" size={17} />Back to cart</Link>
      <header className="fc-header"><div><span className="fc-eyebrow">YOUR NEXT WORKOUT STARTS HERE</span><h1>Review & checkout</h1><p>Great choice. Let’s make it official.</p></div>
        <span className="fc-secure"><Icon name="shield" size={18} />Secure checkout</span></header>
      <ol className="fc-steps" aria-label="Checkout progress"><li className="is-complete"><span><Icon name="check" size={14} /></span>Cart</li><li aria-current="step"><span>2</span>Review & pay</li><li><span>3</span>Confirmation</li></ol>
      {!hasPurchase && !!history.length && <section className="fc-card fg-stack" aria-label="Find your payment result"><h2>Returning from a payment?</h2><p>Your cart does not show membership payments. Choose the payment you want to verify; an empty cart does not mean payment failed.</p>{history.map(payment => <Link key={payment.id} to={`/checkout?payment_checkout_id=${encodeURIComponent(payment.id)}`} className="fg-inline-link">Check {payment.plan_name || payment.kind.toLowerCase().replaceAll('_', ' ')} · {money(payment.total_amount ?? payment.amount, payment.currency)}</Link>)}<Link to="/profile/payments">View all payment history</Link></section>}
      <div className="fc-layout"><div className="fc-content">
        <section className="fc-card" aria-labelledby="fc-visits-title"><div className="fc-section-head"><div><span className="fc-caption">YOUR BOOKING</span><h2 id="fc-visits-title">{currentCheckout ? 'Visits in this checkout' : 'Your workout plans'}</h2></div><span className="fc-count">{visits.length} {visits.length === 1 ? 'visit' : 'visits'}</span></div>
          {visits.map((visit, index) => <CheckoutVisitCard key={visit.id} visit={visit} index={index} editTo={!currentCheckout && cart.find(item => item.id === visit.id)?.can_edit ? `/cart/items/${visit.id}/edit` : undefined} />)}
          {!visits.length && <div className="fc-empty"><Icon name="bag" size={30} /><h3>{currentCheckout ? 'Your checkout is saved' : 'Ready for your next workout?'}</h3><p>{currentCheckout ? 'Your booking links and payment details are available in the payment panel.' : 'There are no new visits in your cart. Choose a gym to get started.'}</p><Link to={currentCheckout ? '/bookings' : '/explore'} className="fg-inline-link">{currentCheckout ? 'My Bookings' : 'Explore gyms'}<Icon name="arrow" size={16} /></Link></div>}
          {!!visits.length && <div className="fc-card-footer"><span><Icon name="clock" size={15} />All visit times are in IST</span><Link to={currentCheckout ? '/bookings' : '/cart'} className="fg-inline-link">{currentCheckout ? 'My Bookings' : 'Edit cart'}<Icon name="arrow" size={15} /></Link></div>}
        </section>
        {currentCheckout && !!newItems.length && <section className="fc-card fc-separate"><h3>Also in your cart</h3><p>These {newItems.length} new {newItems.length === 1 ? 'item is' : 'items are'} not included in this payment.</p><Link to="/cart" className="fg-inline-link">Review separate cart<Icon name="arrow" size={16} /></Link></section>}
        <section className="fc-card fc-customer" aria-label="Booking contact"><span className="fc-contact-icon"><Icon name="user" size={22} /></span><div><span className="fc-caption">BOOKING FOR</span><h3>{user?.first_name} {user?.last_name}</h3><p>{user?.email}</p></div></section>
        <div className="fc-note"><Icon name="ticket" size={20} /><div><strong>One step closer to showing up for yourself.</strong><p>Your booking and entry access are confirmed only after FitiGo verifies your payment.</p></div></div>
      </div>
      <aside className="fc-card fc-payment" aria-labelledby="fc-payment-title"><div className="fc-section-head"><h2 id="fc-payment-title">Order summary</h2><Icon name="bag" size={22} /></div>
        <div className="fc-price-lines"><div><span>{currentCheckout ? 'Checkout subtotal' : 'Cart subtotal'}</span><strong>{total}</strong></div><p>No additional fees or discounts are returned for this checkout.</p></div>
        <div className="fc-total"><div><span>{currentCheckout?.status === 'REVIEW_REQUIRED' || currentCheckout?.status === 'PAID' ? 'Order total' : 'Total to pay'}</span><small>{visits.length} {visits.length === 1 ? 'visit' : 'visits'} · {currentCheckout?.currency ?? currency}</small></div><strong>{total}</strong></div>
        <div className="fc-provider"><span className="fc-provider-icon"><Icon name="shield" size={21} /></span><div><strong>Secure payment</strong><span>Powered by {provider}</span></div>{testMode && <span className="fc-test">Test mode</span>}</div>
        {testMode && <p className="fc-test-note">Test Mode · No real money is charged.</p>}
        {hasPurchase ? <GatewayPayment presentation="checkout" initial={previous} source={{ kind: 'CART', cart_item_ids: cart.length ? cart.map(item => item.id) : undefined }} onCheckout={setSelectedCheckout} onClosed={() => { setSelectedCheckout(undefined); result.retry() }} onPaid={paid => { if (paid.booking_ids[0]) navigate(`/booking/${paid.booking_ids[0]}/success`); else result.retry() }} />
          : <Link to="/explore" className="fg-button fg-button--primary">Find your next workout<Icon name="arrow" size={17} /></Link>}
        {!currentCheckout && !!cart.length && <p className="fc-fine-print">Availability and prices are rechecked before payment. Any unresolved previous payment is checked to help prevent duplicate charges.</p>}
      </aside></div>
      {!!history.length && <details className="fc-card fc-history"><summary><span><Icon name="clock" size={20} />Recent payments <span className="fc-count">{history.length}</span></span><Icon name="down" size={17} /></summary><div className="fc-history-body"><p>Previous purchases are separate from your current cart.</p>{history.map(payment => <article key={payment.id}><div><strong>{money(payment.amount, payment.currency)}</strong><span>{payment.provider} · {payment.status.toLowerCase().replaceAll('_', ' ')}</span></div><small>Reference: {payment.id}</small></article>)}<Link to="/profile/payments" className="fg-inline-link">Review previous payments<Icon name="arrow" size={16} /></Link></div></details>}
    </div>
  }
  return <><Heading eyebrow={checkout ? 'ONE STEP FROM YOUR NEXT WORKOUT' : 'YOUR NEXT WORKOUT, LINED UP'} title={checkout ? 'Review & checkout' : 'Your cart'} subtitle={checkout ? 'Check your visit details before paying with your FitiGo wallet.' : 'A little commitment to feeling good.'} />{!cart.length ? <EmptyState title="Your cart is empty" description="Find a space you love and book your next workout." action={<Link to="/explore" className="fg-button fg-button--primary">Explore gyms</Link>} /> : <div className="fg-two-column"><div className="fg-stack">{cart.map(item => <article className="fg-panel fg-stack" key={item.id}><div className="fg-row"><h3>{item.gym_name ?? 'Gym visit'}</h3><strong>{money(item.total_price, item.currency)}</strong></div><p className="fg-muted">{item.class_name || 'Gym access'}</p><p><Icon name="calendar" size={16} /> {dateLabel(item.booking_date)} · {(item.start_time ?? item.preferred_start_time)?.slice(0, 5)} – {(item.end_time ?? item.preferred_end_time)?.slice(0, 5)} IST</p><p className="fg-muted">{item.member_count} {item.member_count === 1 ? 'member' : 'members'} · {money(item.price_per_person, item.currency)} each</p>{item.visitor_names?.length ? <p className="fg-muted">Visitors: {item.visitor_names.join(", ")}</p> : null}{item.can_edit && <Link to={`/cart/items/${item.id}/edit`} className="fg-inline-link" label={`Edit visit at ${item.gym_name || "gym"}`}>Edit Visit</Link>}{!checkout && <div className="fg-row"><Link to={`/gyms/${item.gym_id}/book/access`} className="fg-inline-link">Book another visit</Link><Button variant="text" loading={mutation.pending} onClick={() => mutation.run(async () => { await bookingService.remove(item.id); result.retry() })}>Remove</Button></div>}</article>)}{checkout && <div className="fg-panel fg-stack"><h3>Customer details</h3><p>{user?.first_name} {user?.last_name}</p><p className="fg-muted">{user?.email}</p><h3>Before you book</h3><p className="fg-muted">Please review each gym’s visit rules. Cancellation eligibility is determined by the gym and the booking service. A wallet refund is not guaranteed.</p>{cart.map(item => <Link key={item.id} to={`/gyms/${item.gym_id}`} className="fg-inline-link">View {item.gym_name ?? 'gym'} policies <Icon name="arrow" size={16} /></Link>)}</div>}</div><aside className="fg-panel fg-stack fg-sidebar-sticky"><h2>Order summary</h2><div className="fg-total-row"><span>Subtotal</span><strong>{money(totalMinor / 100, currency)}</strong></div><p className="fg-muted">No additional fees or discounts are returned for this cart.</p><hr className="fg-divider" /><div className="fg-total-row"><h3>Total</h3><strong className="fg-price">{money(totalMinor / 100, currency)}</strong></div>{checkout ? <><hr className="fg-divider" /><div className="fg-row"><span><Icon name="wallet" size={18} /> Wallet balance</span><strong>{money(wallet!.balance, wallet!.currency)}</strong></div>{sufficient ? <Button disabled={mutation.pending} onClick={() => setConfirm(true)}>Pay {money(totalMinor / 100, currency)} using wallet</Button> : <><Alert>Insufficient wallet balance. Recharge your wallet before paying.</Alert><Link to="/wallet/recharge?returnTo=%2Fcheckout" className="fg-button fg-button--primary">Recharge wallet</Link></>}<Link to="/cart" className="fg-inline-link">Back to cart</Link></> : <Link to="/checkout" className="fg-button fg-button--primary">Proceed to checkout <Icon name="arrow" size={18} /></Link>}{mutation.error && <Alert>{mutation.error}<Button variant="text" onClick={result.retry}>Review latest balance and cart</Button></Alert>}<small className="fg-muted">Availability and wallet balance are checked again at payment.</small></aside></div>}{confirm && <Modal title="Confirm your booking" onClose={() => { if (!mutation.pending) setConfirm(false) }}><div className="fg-stack"><p>Pay <strong>{money(totalMinor / 100, currency)}</strong> from your FitiGo wallet for {cart.length} {cart.length === 1 ? 'visit' : 'visits'}?</p>{mutation.error && <Alert>{mutation.error}</Alert>}<Button loading={mutation.pending} onClick={pay}>Confirm payment</Button><Button disabled={mutation.pending} variant="text" onClick={() => setConfirm(false)}>Go back</Button></div></Modal>}</>
}