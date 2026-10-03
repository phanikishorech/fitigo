import { useRef } from 'react'
import { Alert, Button, Heading } from '../../components/common/UI'
import { MembershipBack, MembershipNotice } from '../../components/membership/MembershipUI'
import { MembershipPlanCard, PlanEmptyState, PlanErrorState, PlanSkeleton } from '../../components/membership/MembershipPlanCard'
import { useMutation, useResource } from '../../hooks/useResource'
import { usePlanRefresh } from '../../hooks/usePlanRefresh'
import { planLoadError, platformMembershipService } from '../../services/platformMembershipService'
import { navigate } from '../../router'

export default function MultiGymPlansPage() {
  const result = useResource(async () => { try { return await platformMembershipService.catalog() } catch (error) { throw new Error(planLoadError(error)) } }, 'multi-gym-catalog')
  const mutation = useMutation()
  const keys = useRef(new Map<number, string>())
  const offerBoundary = result.data?.items.flatMap(plan => plan.offer ? [plan.offer.valid_until] : []).sort((a, b) => Date.parse(a) - Date.parse(b))[0]
  usePlanRefresh(result.retry, offerBoundary, result.data?.server_time)
  const choose = (id: number) => mutation.run(async () => {
    // Preserve the key for retries after an ambiguous network failure.
    if (!keys.current.has(id)) keys.current.set(id, crypto.randomUUID())
    const order = await platformMembershipService.createOrder(id, keys.current.get(id)!)
    navigate(`/membership/checkout?orderId=${encodeURIComponent(order.id)}`)
  })
  return <div className="fm-page"><MembershipBack /><Heading title="Multi-Gym Plans" subtitle="One membership. Multiple gyms." />
    {result.loading ? <PlanSkeleton /> : result.error ? <PlanErrorState message={result.error} retry={result.retry} /> : !result.data?.items.length ? <PlanEmptyState /> : <>
      <MembershipNotice>{result.data.checkout_available ? 'Controlled MVP: pay using wallet test credits only. No real-money or external payment is taken. Choosing a plan opens checkout for review.' : 'Membership checkout is unavailable in this environment. External payments remain disabled.'}</MembershipNotice>
      {mutation.error && <Alert>{mutation.error} <Button variant="text" onClick={result.retry}>Refresh plans</Button></Alert>}
      <div className="fm-plan-grid">{result.data.items.map(plan => <MembershipPlanCard key={plan.id} plan={plan}><Button className="fm-full" disabled={mutation.pending} onClick={() => choose(plan.id)} aria-label={`Choose Plan: ${plan.name}`}>{mutation.pending ? 'Preparing review…' : 'Choose Plan'}</Button></MembershipPlanCard>)}</div>
    </>}
  </div>
}