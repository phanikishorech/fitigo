import { useRef, useState } from 'react'
import { getAccessToken } from '../../auth'
import { openAuthModal } from '../../authUi'
import { useResource } from '../../hooks/useResource'
import { membershipService } from '../../services/accountService'
import { gymService } from '../../services/gymService'
import { money } from '../../services/client'
import { navigate } from '../../router'
import { Button, EmptyState, ErrorState, Heading, Link, Skeleton } from '../../components/common/UI'
import Icon from '../../components/common/Icon'
import WalletMembershipPayment from '../../components/membership/WalletMembershipPayment'

export function MembershipPlansPage({ gymId, checkout = false }: { gymId: number; checkout?: boolean }) {
  const result = useResource(async () => { const [gym, plans] = await Promise.all([gymService.details(gymId), membershipService.plans(gymId)]); return { gym, plans: plans.filter(p => p.is_active) } }, String(gymId))
  const [selected, setSelected] = useState(() => Number(new URLSearchParams(window.location.search).get('planId')) || 0)
  if (result.loading) return <Skeleton cards={3} />
  if (result.error) return <ErrorState message={result.error} retry={result.retry} />
  const { gym, plans } = result.data!
  const plan = plans.find(item => item.id === selected)
  const next = () => { if (!plan) return; const to = `/membership/checkout?gymId=${gymId}&planId=${plan.id}`; if (!getAccessToken()) openAuthModal(to); else navigate(to) }
  return <><Link to={`/gyms/${gymId}`} className="fg-inline-link"><Icon name="back" />{gym.gym_name}</Link><Heading eyebrow="YOUR ROUTINE STARTS HERE" title={checkout ? 'Your membership, ready to go' : 'Choose your membership'} subtitle={`Make ${gym.gym_name} part of your everyday.`} />
    {!plans.length ? <EmptyState title="No memberships available" action={<Link to={`/gyms/${gymId}/book/access`}>Book a visit</Link>} /> : checkout && plan ? <SingleWalletCheckout gymId={gymId} planId={plan.id} /> : <div className="fg-two-column"><div className="fg-stack">
      {plans.map(item => <button type="button" key={item.id} className={`fg-plan ${selected === item.id ? 'is-active' : ''}`} aria-pressed={selected === item.id} onClick={() => setSelected(item.id)}><h2>{item.name}</h2><p>{item.duration_days} days of membership</p><p className="fg-price">{money(item.price, item.currency)}</p>{item.description && <p>{item.description}</p>}</button>)}
    </div><aside className="fg-panel fg-stack"><h3>{gym.gym_name}</h3><p>{plan ? plan.name : 'Choose a plan to continue.'}</p><Button disabled={!plan} onClick={next}>Continue</Button></aside></div>}
  </>
}
function SingleWalletCheckout({ gymId, planId }: { gymId: number; planId: number }) {
  const result = useResource(() => membershipService.quote(gymId, planId), `single-wallet:${gymId}:${planId}`)
  const key = useRef(crypto.randomUUID())
  if (result.loading) return <Skeleton cards={2} />
  if (result.error) return <ErrorState message={result.error} retry={result.retry} />
  const quote = result.data!
  return <div className="fg-two-column"><section className="fg-panel fg-stack"><h2>{quote.plan.name}</h2><p>{quote.plan.duration_value} days · This gym only</p><strong className="fg-price">{money(quote.plan.final_price, quote.plan.currency)}</strong><p>Current price supplied by FitiGo.</p></section><aside className="fg-panel"><WalletMembershipPayment amount={quote.plan.final_price} currency={quote.plan.currency} balance={quote.wallet_balance} walletCurrency={quote.wallet_currency} available={quote.payment_available} refresh={result.retry} pay={async () => {
    const membership = await membershipService.purchase(gymId, planId, quote.quote_token, key.current)
    navigate(`/membership/success?id=${membership.id}`)
  }} /></aside></div>
}
export { default } from './MembershipOverview'