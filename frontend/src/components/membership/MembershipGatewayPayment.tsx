import { useEffect } from 'react'
import { useResource } from '../../hooks/useResource'
import { paymentService, type MembershipSource, type PaymentCheckout } from '../../services/paymentService'
import GatewayPayment from '../common/GatewayPayment'
import { Alert, Button, Link } from '../common/UI'

export default function MembershipGatewayPayment({ source, onPaid, onCheckout, refresh, plansPath }: {
  source: MembershipSource; onPaid: (checkout: PaymentCheckout) => void; onCheckout?: (checkout: PaymentCheckout) => void; refresh: () => void; plansPath: string
}) {
  const recovery = useResource(() => paymentService.recoverMembership(source), JSON.stringify(source))
  useEffect(() => { if (recovery.data?.checkout) onCheckout?.(recovery.data.checkout) }, [recovery.data?.checkout, onCheckout])
  if (recovery.loading) return <p role="status">Checking for an unfinished membership payment…</p>
  if (recovery.error) return <div className="fg-stack"><Alert>{recovery.error} No new payment has been started.</Alert><Button variant="secondary" onClick={recovery.retry}>Retry payment recovery</Button></div>
  const previous = recovery.data?.checkout ?? undefined
  return <div className="fg-stack">
    {(previous || source.accepted_quote) ? <GatewayPayment key={previous?.id ?? JSON.stringify(source)} source={source} initial={previous} onPaid={onPaid} onCheckout={onCheckout} matchesSelection={recovery.data?.matches_selection ?? true}
      onClosed={() => { recovery.retry(); refresh() }} closedLabel="Review plan and payment method" /> : <Alert>This plan is unavailable. Choose another plan to continue.</Alert>}
    <Link to={plansPath} className="fg-inline-link">Browse other plans</Link>
  </div>
}