import { useState } from 'react'
import { request } from '../services/client'
import { useAdminResource } from './hooks'
import { Alert, DataCard, Details, EmptyState, Pagination, Resource } from './UI'
import { istDateTime } from '../utils/membership'

type Delivery={id:number;user_id:number;kind:string;email_status:string;attempts:number;error_code:string|null;created_at:string;accepted_at:string|null}
export default function NotificationDelivery() {
  const [page,setPage]=useState(0)
  const resource=useAdminResource(()=>request<{enabled:boolean;items:Delivery[];total:number}>(`/notifications/delivery-status?limit=20&offset=${page*20}`,{cache:'no-store'}),`delivery-status:${page}`)
  return <DataCard title="Email processing status"><Alert>Accepted does not mean delivered. UNKNOWN sends need operator investigation and are never automatically resent. This screen cannot send or retry messages.</Alert><Resource resource={resource}>{data=><>{!data.enabled ? <p>Notification processing is disabled in this deployment.</p> : <>{data.items.length ? data.items.map(row=><article key={row.id}><Details rows={[["Notification",`#${row.id}`],['Recipient',`User #${row.user_id}`],['Event',row.kind],['Email state',row.email_status],['Attempts',row.attempts],['Recorded',istDateTime(row.created_at)],['Provider accepted',row.accepted_at?istDateTime(row.accepted_at):'Not confirmed'],['Issue',row.error_code||'None recorded']]} /></article>) : <EmptyState title="No email jobs" />}<Pagination page={page} count={data.items.length} hasMore={(page+1)*20<data.total} onPage={setPage} /></>}</>}</Resource></DataCard>
}