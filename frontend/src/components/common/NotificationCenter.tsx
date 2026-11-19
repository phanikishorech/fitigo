import { useState } from 'react'
import { useMutation, useResource } from '../../hooks/useResource'
import { request } from '../../services/client'
import { istDateTime } from '../../utils/membership'
import { Alert, Button, ErrorState, Skeleton } from './UI'
import { notifyActivity } from '../../services/customerActivity'

type Preferences = { enabled: boolean; operational_email: boolean; email_available: boolean; message: string }
type Item = { id: number; title: string; body: string; category: string; created_at: string; read_at: string | null; email_status: string; error_code: string | null }
type Inbox = { enabled: boolean; items: Item[]; total: number; unread_count: number }
export default function NotificationCenter({ inbox = true, preferences = true }: { inbox?: boolean; preferences?: boolean }) {
  const [legacy, setLegacy] = useState(false)
  return <section className="fg-panel fg-stack"><h2>{inbox ? 'Notifications' : 'Notification preferences'}</h2>{preferences && <PreferencesForm />}{inbox && <><InboxList /><Button variant="secondary" onClick={() => setLegacy(value => !value)}>{legacy ? 'Hide' : 'View'} recorded event history</Button>{legacy && <LegacyHistory />}</>}</section>
}
function LegacyHistory() {
  const [page,setPage]=useState(0)
  const resource=useResource(() => request<{id:number;event_type:string;status:string;created_at:string}[]>(`/notifications/me?limit=20&offset=${page*20}`,{cache:'no-store'}),`legacy-notifications:${page}`)
  return <div className="fg-stack"><p>Historical event labels are not verified delivery or read status. No old event is automatically sent by enabling notifications.</p>{resource.loading ? <Skeleton cards={1} /> : resource.error ? <ErrorState message={resource.error} retry={resource.retry} /> : <>{resource.data?.map(row=><p key={row.id}>#{row.id} · {row.event_type.replaceAll('_',' ')} · Recorded label: {row.status} · {istDateTime(row.created_at)}</p>)}{!resource.data?.length && <p>No recorded events on this page.</p>}<div className="fg-actions"><Button disabled={page===0} onClick={()=>setPage(p=>p-1)}>Previous events</Button><Button disabled={resource.data?.length!==20} onClick={()=>setPage(p=>p+1)}>Next events</Button></div></>}</div>
}
function PreferencesForm() {
  const resource = useResource(() => request<Preferences>('/notifications/preferences', { cache: 'no-store' }), 'notification-preferences')
  const mutation = useMutation(); const [saved, setSaved] = useState(false)
  if (resource.loading) return <Skeleton cards={1} />
  if (resource.error) return <ErrorState message={resource.error} retry={resource.retry} />
  const data = resource.data!
  if (!data.enabled) return <p>Notification preferences and inbox read tracking are not enabled in this deployment. No settings have been changed.</p>
  return <div className="fg-stack"><p>{data.message}</p><p>Optional operational email: <strong>{data.operational_email ? 'On' : 'Off'}</strong>. Channel: {data.email_available ? 'configured' : 'unavailable or email unverified'}.</p>
    <Button variant="secondary" loading={mutation.pending} disabled={!data.email_available && !data.operational_email} onClick={() => { setSaved(false); void mutation.run(async () => { await request('/notifications/preferences', { method: 'PATCH', body: JSON.stringify({ operational_email: !data.operational_email }) }); setSaved(true); resource.retry() }) }}>{data.operational_email ? 'Turn off operational email' : 'Enable operational email'}</Button>
    <p>Security notices are not optional. SMS and push notification preferences are not available.</p>{mutation.error && <Alert>{mutation.error}</Alert>}{saved && <p role="status">Notification preference saved.</p>}
  </div>
}
function InboxList() {
  const [page, setPage] = useState(0); const [unread, setUnread] = useState(false); const mutation = useMutation()
  const resource = useResource(() => request<Inbox>(`/notifications/inbox?limit=20&offset=${page * 20}&unread=${unread}`, { cache: 'no-store' }), `notification-inbox:${page}:${unread}`)
  return <div className="fg-stack"><label><input type="checkbox" checked={unread} onChange={e => { setUnread(e.target.checked); setPage(0) }} /> Unread only</label>
    <Button variant="secondary" onClick={resource.retry}>Refresh notifications</Button>
    {resource.loading ? <Skeleton cards={1} /> : resource.error ? <ErrorState message={resource.error} retry={resource.retry} /> : resource.data?.enabled ? <>
      <p>{resource.data.unread_count} unread. Read status is separate from email status. Accepted means accepted by the email provider, not delivered to an inbox.</p>
      {!resource.data.items.length && <p>No notifications on this page.</p>}
      {resource.data.items.map(item => <article className="fg-panel fg-stack" key={item.id}><h3>{item.title}</h3><p>{item.body}</p><small>{istDateTime(item.created_at)} · {item.category}</small><p>{item.read_at ? 'Read' : 'Unread'} · Email: {item.email_status.replaceAll('_', ' ')}</p>{item.error_code && <p>{item.error_code.replaceAll('_', ' ')}. Uncertain sends are not automatically resent.</p>}{!item.read_at && <Button variant="secondary" loading={mutation.pending} onClick={() => void mutation.run(async () => { await request(`/notifications/inbox/${item.id}/read`, { method: 'POST' }); notifyActivity('notifications'); resource.retry() })}>Mark read</Button>}</article>)}
      <div className="fg-actions"><Button variant="secondary" disabled={page === 0} onClick={() => setPage(p => p - 1)}>Previous</Button><span>Page {page + 1}</span><Button variant="secondary" disabled={(page + 1) * 20 >= resource.data.total} onClick={() => setPage(p => p + 1)}>Next</Button></div>
    </> : <p>Inbox is disabled until the notification migration is deployed.</p>}{mutation.error && <Alert>{mutation.error}</Alert>}
  </div>
}