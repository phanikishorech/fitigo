import { businessService } from './businessService'
import { useAdminResource } from './hooks'
import { DataCard, Details, Link, Resource } from './UI'
import { dateLabel } from '../services/client'
import { businessCash } from './BusinessOverview'

export default function CustomerActivity({ id }: { id: number }) {
  const resource = useAdminResource(() => businessService.customer(id), `admin-customer-activity:${id}`)
  return <Resource resource={resource}>{data => <><DataCard title="Customer wallet"><Details rows={[["Unused wallet balance", businessCash(data.wallet_balance)], ['Payment records', data.wallet_mode || 'No payment environment recorded']]} /></DataCard><DataCard title="Memberships"><Link to={`/admin/memberships?user_id=${id}`}>View all {data.memberships.total} memberships</Link>{data.memberships.items.map(row => <p key={row.id}>{row.kind.replaceAll('_', ' ')} · {row.status} · Valid until {dateLabel(row.valid_until)} · {row.gym_name || 'Eligible partner gyms'}</p>)}</DataCard><DataCard title="Recent bookings">{data.bookings.length ? data.bookings.map(row => <p key={row.id}><Link to={`/admin/bookings/${row.id}`}>Booking #{row.id}</Link> · {dateLabel(row.date)} · {row.status} · {businessCash(row.amount)}</p>) : <p>No booking history yet.</p>}</DataCard></>}</Resource>
}