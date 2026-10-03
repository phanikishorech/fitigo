import { Alert, Button, Heading, Link } from '../../components/common/UI'
import { MembershipBack, MembershipFacts, MembershipNotice, MembershipPanel } from '../../components/membership/MembershipUI'
import { MembershipPlanCard, PlanErrorState, PlanSkeleton } from '../../components/membership/MembershipPlanCard'
import { useResource } from '../../hooks/useResource'
import { usePlanRefresh } from '../../hooks/usePlanRefresh'
import { platformMembershipService } from '../../services/platformMembershipService'
import { membershipDate } from '../../utils/membership'
import WalletMembershipPayment, { TestCreditNotice } from '../../components/membership/WalletMembershipPayment'
import { navigate } from '../../router'

export default function MembershipOrderPage({ orderId }: { orderId: string }) {
  const result = useResource(() => platformMembershipService.order(orderId), `membership-order:${orderId}`)
  usePlanRefresh(result.retry, result.data?.current_plan?.offer?.valid_until)
  const order = result.data
  return <div className="fm-page"><MembershipBack to="/membership/multi-gym/plans">Multi-Gym plans</MembershipBack><Heading title="Review your membership" subtitle="Your selected plan, with pricing confirmed by FitiGo." />
    {result.loading ? <PlanSkeleton /> : result.error ? <PlanErrorState message={result.error} retry={result.retry} /> : order && <>
      <TestCreditNotice />
      {order.membership_id && <MembershipNotice>Wallet payment recorded. <Link to={`/membership/${order.membership_id}`}>View Membership</Link></MembershipNotice>}
      {order.requires_review && <Alert>{order.current_plan ? 'This plan has changed since you selected it. The latest backend price and terms are shown below.' : 'This plan is no longer available. Choose another plan to continue browsing.'}</Alert>}
      <div className="fg-two-column fm-order-layout"><div>{order.current_plan ? <MembershipPlanCard plan={order.current_plan} /> : <MembershipPanel title="Plan unavailable"><p>{order.plan.name}</p><Link to="/membership/multi-gym/plans" className="fg-button fg-button--primary">View Multi-Gym Plans</Link></MembershipPanel>}</div>
        <MembershipPanel title="Order review"><MembershipFacts rows={[["Order", order.id], ['Created', membershipDate(order.created_at)], ['Payment', order.payment_status], ['Membership', order.membership_id ? `#${order.membership_id}` : 'Not activated']]} />
          {!order.membership_id && order.current_plan && <WalletMembershipPayment amount={order.current_plan.final_price} currency={order.current_plan.currency} balance={order.wallet_balance || '0.00'} walletCurrency={order.wallet_currency || order.current_plan.currency} available={order.payment_available && !!order.quote_token} refresh={result.retry} pay={async () => {
            const paid = await platformMembershipService.payWallet(order.id, order.quote_token!)
            if (paid.membership_id) navigate(`/membership/success?id=${paid.membership_id}`)
            else result.retry()
          }} />}
          {!order.current_plan && <Button variant="secondary" onClick={result.retry}>Refresh current price</Button>}
        </MembershipPanel>
      </div>
    </>}
  </div>
}