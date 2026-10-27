import type { OwnerDashboardSummary } from '../screens/GymOwner/api'
import { money } from '../services/client'
import { MetricCard } from './UI'

export const categoryLabels: Record<string, string> = { fitigo_member: 'Multi-Gym member', single_gym_membership: 'Single-Gym membership', individual_booking: 'Individual booking', upcoming: 'Upcoming bookings', attended: 'Attended bookings', cancelled: 'Cancelled bookings', no_show: 'Not attended / no-show', pending_payment: 'Pending payment', expired: 'Expired', unresolved: 'Unresolved' }
export function PrimaryMetrics({ data }: { data: OwnerDashboardSummary }) {
  return <div className="ow-metric-grid ow-primary-grid">
    <MetricCard icon="check" label="Visits completed" value={data.visits.total} note="Successful check-ins in this period" />
    <MetricCard icon="clock" label="Upcoming visits" value={data.upcoming_visits} note="Paid future visitor places; not yet checked in" />
    <MetricCard icon="wallet" label="Total revenue" value={money(data.revenue.total)} note={`Paid memberships + checked-in bookings · ${data.revenue.mode}${data.revenue.mode === 'test' ? ' · No real money' : ''}`} emphasis />
  </div>
}
export function RevenueBasis({ revenue }: { revenue: OwnerDashboardSummary['revenue'] }) {
  return <details className="ow-revenue-basis"><summary>Revenue calculation & exclusions</summary>
    <p>Purchase dates in the selected period (IST), using verified payments in the configured {revenue.mode} mode only.{revenue.mode === 'test' && ' Test payments do not represent real money.'} Total = confirmed Single-Gym membership payments + paid bookings with a successful check-in. Membership payments count once without requiring a visit.</p>
    <p>Upcoming or unscanned bookings contribute zero revenue. Manual attendance alone is not proof of check-in. A group booking payment counts once after its first successful visitor check-in, never once per scan. A later check-in makes the booking eligible in its original purchase-date period, not the check-in-date period.</p>
    <p>Fully refunded sales excluded: {money(revenue.fully_refunded_sales)}. Partially refunded records excluded: {revenue.partial_refund_count}; exact net amounts are not stored. Other excluded paid records (no eligible check-in, wallet credit, legacy or review-required): {revenue.excluded_paid_records}. Payments from the other mode are outside this report.</p>
    <p>Cancelled and no-show bookings are excluded even if paid. Multi-Gym sales have no gym-allocation model and are not included. This is not a settlement or payout report; no fee or tax amounts are inferred.</p>
  </details>
}