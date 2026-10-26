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
import { paymentService } from '../../services/paymentService'

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
  const mutation = useMutation()
  if (result.loading) return <Skeleton cards={2} />
  if (result.error) return <ErrorState message={result.error} retry={result.retry} />
  const { cart, wallet, user, gateway, payments } = result.data!
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
  if (checkout && gateway?.enabled) return <>
    <Heading title="Review & checkout" subtitle={`${gateway.provider === 'CASHFREE' ? 'Cashfree' : 'Razorpay'} · ${gateway.mode === 'test' ? 'Test Mode · No real money is charged.' : 'Live Mode · Real payments.'}`} />
    <div className="fg-two-column"><div className="fg-stack">{cart.map(item => <article className="fg-panel fg-stack" key={item.id}><h3>{item.gym_name || 'Gym visit'}</h3><p>{dateLabel(item.booking_date)} · {(item.start_time || item.preferred_start_time)?.slice(0, 5)} IST</p><p>{item.member_count} visitors · {money(item.total_price, item.currency)}</p></article>)}
      {!cart.length && <p>Your cart has no new items. Resume or refresh a recent payment below, or view My Bookings.</p>}
      <Link to="/bookings" className="fg-inline-link">My Bookings</Link><Link to="/cart" className="fg-inline-link">Edit cart</Link>
    </div><aside className="fg-panel fg-stack"><h2>Payment</h2><p>{user?.first_name} {user?.last_name} · {user?.email}</p>
      {!!cart.length && <GatewayPayment source={{ kind: 'CART' }} onPaid={paid => { if (paid.booking_ids[0]) navigate(`/booking/${paid.booking_ids[0]}/success`); else result.retry() }} />}
      {!cart.length && !payments.length && <Link to="/explore">Find a gym</Link>}
    </aside></div>
    {!!payments.length && <section className="fg-stack"><h2>Recent payments</h2>{payments.map(payment => <article className="fg-panel" key={payment.id}><GatewayPayment initial={payment} /></article>)}</section>}
  </>
  return <><Heading eyebrow={checkout ? 'ONE STEP FROM YOUR NEXT WORKOUT' : 'YOUR NEXT WORKOUT, LINED UP'} title={checkout ? 'Review & checkout' : 'Your cart'} subtitle={checkout ? 'Check your visit details before paying with your FitiGo wallet.' : 'A little commitment to feeling good.'} />{!cart.length ? <EmptyState title="Your cart is empty" description="Find a space you love and book your next workout." action={<Link to="/explore" className="fg-button fg-button--primary">Explore gyms</Link>} /> : <div className="fg-two-column"><div className="fg-stack">{cart.map(item => <article className="fg-panel fg-stack" key={item.id}><div className="fg-row"><h3>{item.gym_name ?? 'Gym visit'}</h3><strong>{money(item.total_price, item.currency)}</strong></div><p className="fg-muted">{item.class_name || 'Gym access'}</p><p><Icon name="calendar" size={16} /> {dateLabel(item.booking_date)} · {(item.start_time ?? item.preferred_start_time)?.slice(0, 5)} – {(item.end_time ?? item.preferred_end_time)?.slice(0, 5)} IST</p><p className="fg-muted">{item.member_count} {item.member_count === 1 ? 'member' : 'members'} · {money(item.price_per_person, item.currency)} each</p>{!checkout && <div className="fg-row"><Link to={`/gyms/${item.gym_id}/book/access`} className="fg-inline-link">Book another visit</Link><Button variant="text" loading={mutation.pending} onClick={() => mutation.run(async () => { await bookingService.remove(item.id); result.retry() })}>Remove</Button></div>}</article>)}{checkout && <div className="fg-panel fg-stack"><h3>Customer details</h3><p>{user?.first_name} {user?.last_name}</p><p className="fg-muted">{user?.email}</p><h3>Before you book</h3><p className="fg-muted">Please review each gym’s visit rules. Cancellation eligibility is determined by the gym and the booking service. A wallet refund is not guaranteed.</p>{cart.map(item => <Link key={item.id} to={`/gyms/${item.gym_id}`} className="fg-inline-link">View {item.gym_name ?? 'gym'} policies <Icon name="arrow" size={16} /></Link>)}</div>}</div><aside className="fg-panel fg-stack fg-sidebar-sticky"><h2>Order summary</h2><div className="fg-total-row"><span>Subtotal</span><strong>{money(totalMinor / 100, currency)}</strong></div><p className="fg-muted">No additional fees or discounts are returned for this cart.</p><hr className="fg-divider" /><div className="fg-total-row"><h3>Total</h3><strong className="fg-price">{money(totalMinor / 100, currency)}</strong></div>{checkout ? <><hr className="fg-divider" /><div className="fg-row"><span><Icon name="wallet" size={18} /> Wallet balance</span><strong>{money(wallet!.balance, wallet!.currency)}</strong></div>{sufficient ? <Button disabled={mutation.pending} onClick={() => setConfirm(true)}>Pay {money(totalMinor / 100, currency)} using wallet</Button> : <><Alert>Insufficient wallet balance. Recharge your wallet before paying.</Alert><Link to="/wallet/recharge?returnTo=%2Fcheckout" className="fg-button fg-button--primary">Recharge wallet</Link></>}<Link to="/cart" className="fg-inline-link">Back to cart</Link></> : <Link to="/checkout" className="fg-button fg-button--primary">Proceed to checkout <Icon name="arrow" size={18} /></Link>}{mutation.error && <Alert>{mutation.error}<Button variant="text" onClick={result.retry}>Review latest balance and cart</Button></Alert>}<small className="fg-muted">Availability and wallet balance are checked again at payment.</small></aside></div>}{confirm && <Modal title="Confirm your booking" onClose={() => { if (!mutation.pending) setConfirm(false) }}><div className="fg-stack"><p>Pay <strong>{money(totalMinor / 100, currency)}</strong> from your FitiGo wallet for {cart.length} {cart.length === 1 ? 'visit' : 'visits'}?</p>{mutation.error && <Alert>{mutation.error}</Alert>}<Button loading={mutation.pending} onClick={pay}>Confirm payment</Button><Button disabled={mutation.pending} variant="text" onClick={() => setConfirm(false)}>Go back</Button></div></Modal>}</>
}