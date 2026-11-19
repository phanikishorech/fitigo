import { useState } from 'react'
import { useResource } from '../hooks/useResource'
import { request } from '../services/client'
import { istDateTime } from '../utils/membership'
import { Button, DataCard, Details, ErrorState, Skeleton } from './UI'

type Transfer = { reference: string; membership_id: number; original_customer_id: number; receiving_customer_id: number; current_owner_id: number; transferred_by: number; status: string; transferred_at: string; start_at: string; end_at: string; original_end_at: string; purchase_reference: string | null }
export default function MembershipTransfers() {
  const [page, setPage] = useState(0)
  const data = useResource(() => request<{ enabled: boolean; items: Transfer[]; has_more: boolean }>(`/admin/memberships/transfers?limit=20&offset=${page * 20}`, { cache: 'no-store' }), `transfer-audit:${page}`)
  return <DataCard title="Membership transfer history">{data.loading ? <Skeleton /> : data.error ? <ErrorState message={data.error} retry={data.retry} /> : !data.data?.enabled ? <p>Transfer history requires the policy migration.</p> : <>{!data.data.items.length && <p>No completed transfers on this page.</p>}{data.data.items.map(row => <Details key={row.reference} rows={[["Membership", `#${row.membership_id}`], ['Original customer', `#${row.original_customer_id}`], ['Recipient', `#${row.receiving_customer_id}`], ['Current owner', `#${row.current_owner_id}`], ['Transferred by', `#${row.transferred_by}`], ['Status', row.status], ['Transferred', istDateTime(row.transferred_at)], ['Original start', istDateTime(row.start_at)], ['Validity at transfer', istDateTime(row.end_at)], ['Original expiry', istDateTime(row.original_end_at)], ['Purchase reference', row.purchase_reference || 'Not linked'], ['Transfer reference', row.reference]]} />)}<div className="fg-row"><Button variant="secondary" disabled={!page} onClick={() => setPage(value => value - 1)}>Previous transfers</Button><Button variant="secondary" disabled={!data.data.has_more} onClick={() => setPage(value => value + 1)}>Next transfers</Button></div></>}</DataCard>
}