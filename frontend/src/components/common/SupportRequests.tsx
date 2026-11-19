import { useRef, useState } from 'react'
import { request } from '../../services/client'
import { useMutation, useResource } from '../../hooks/useResource'
import { istDateTime } from '../../utils/membership'
import { Alert, Button, ErrorState, Skeleton } from './UI'

type Ticket = { id: number; user_id: number; category: string; subject: string; status: string; version: number; updated_at: string }
type Detail = Ticket & { messages: { id: number; author_kind: string; body: string; created_at: string }[]; message_total: number; can_reply: boolean; can_change_status: boolean }
const statuses = ['OPEN', 'WAITING_USER', 'RESOLVED']

export type SupportPrefill = { category: string; subject: string; body: string }

export default function SupportRequests({ admin = false, prefill }: { admin?: boolean; prefill?: SupportPrefill }) {
  const capability = useResource(() => request<{ ticketing_available: boolean }>('/meta/support', { cache: 'no-store' }), 'support-availability')
  if (capability.loading) return <Skeleton cards={1} />
  if (capability.error) return <ErrorState message={capability.error} retry={capability.retry} />
  if (!capability.data?.ticketing_available) return <p>In-app support requests are not enabled in this deployment. No request has been submitted.</p>
  return <TicketList admin={admin} prefill={prefill} />
}

function TicketList({ admin, prefill }: { admin: boolean; prefill?: SupportPrefill }) {
  const base = admin ? '/admin/support/tickets' : '/support/tickets'
  const [selected, setSelected] = useState<number | null>(null)
  const [page, setPage] = useState(0); const [status, setStatus] = useState(''); const [q, setQ] = useState(''); const [search, setSearch] = useState('')
  const resource = useResource(() => request<{ items: Ticket[]; total: number }>(`${base}?limit=20&offset=${page * 20}&q=${encodeURIComponent(q)}${status ? `&status=${status}` : ''}`, { cache: 'no-store' }), `support-list:${base}:${page}:${status}:${q}`)
  if (selected !== null) return <Conversation key={`${base}:${selected}`} base={base} id={selected} back={() => { setSelected(null); resource.retry() }} />
  return <section className="fg-stack"><h2>{admin ? 'Support queue' : 'My support requests'}</h2>
    <p>Messages are visible to the requester and authorized administrators. Do not include passwords, OTPs, QR tokens or payment credentials. No attachments, email delivery or response-time promise.</p>
    {!admin && <NewTicket onCreated={setSelected} prefill={prefill} />}
    <form className="fg-stack" onSubmit={e => { e.preventDefault(); setQ(search.trim()); setPage(0) }}><label className="fg-field">Search subject<input value={search} maxLength={100} onChange={e => setSearch(e.target.value)} /></label><Button type="submit" variant="secondary">Search requests</Button></form>
    <label className="fg-field">Status<select value={status} onChange={e => { setStatus(e.target.value); setPage(0) }}><option value="">All statuses</option>{statuses.map(s => <option key={s}>{s}</option>)}</select></label>
    <Button variant="secondary" onClick={resource.retry}>Refresh requests</Button>
    {resource.loading ? <Skeleton cards={1} /> : resource.error ? <ErrorState message={resource.error} retry={resource.retry} /> : <>
      {!resource.data?.items.length && <p>No support requests match.</p>}
      {resource.data?.items.map(ticket => <article key={ticket.id} className="fg-panel fg-stack"><h3 style={{ overflowWrap: 'anywhere' }}>#{ticket.id} · {ticket.subject}</h3><p>{ticket.category} · {ticket.status} · {istDateTime(ticket.updated_at)}</p>{admin && <p>Requester #{ticket.user_id}</p>}<Button variant="secondary" onClick={() => setSelected(ticket.id)}>Open request #{ticket.id}</Button></article>)}
      <div className="fg-actions"><Button disabled={page === 0} onClick={() => setPage(p => p - 1)}>Previous requests</Button><span>Page {page + 1}</span><Button disabled={(page + 1) * 20 >= (resource.data?.total || 0)} onClick={() => setPage(p => p + 1)}>Next requests</Button></div>
    </>}
  </section>
}

function NewTicket({ onCreated, prefill }: { onCreated: (id: number) => void; prefill?: SupportPrefill }) {
  const mutation = useMutation(); const attempt = useRef<{ payload: string; key: string } | null>(null)
  return <details className="fg-panel" open={prefill ? true : undefined}><summary>Create a support request</summary><form className="fg-stack" onSubmit={e => {
    e.preventDefault(); const form = new FormData(e.currentTarget)
    const payload = JSON.stringify({ category: String(form.get('category')), subject: String(form.get('subject')).trim(), body: String(form.get('body')).trim() })
    if (!attempt.current || attempt.current.payload !== payload) attempt.current = { payload, key: crypto.randomUUID() }
    const current = attempt.current
    void mutation.run(async () => { const ticket = await request<Ticket>('/support/tickets', { method: 'POST', headers: { 'Idempotency-Key': current.key }, body: current.payload }); onCreated(ticket.id) })
  }}><label className="fg-field">Category<select name="category" defaultValue={prefill?.category} disabled={mutation.pending}>{['ACCOUNT', 'BOOKING', 'GYM', 'TECHNICAL', 'OTHER'].map(c => <option key={c}>{c}</option>)}</select></label>
    <label className="fg-field">Subject<input name="subject" defaultValue={prefill?.subject} required maxLength={120} disabled={mutation.pending} /></label><label className="fg-field">Describe the issue<textarea name="body" defaultValue={prefill?.body} required maxLength={2000} rows={5} disabled={mutation.pending} /></label>
    {mutation.error && <Alert>{mutation.error}</Alert>}<Button type="submit" loading={mutation.pending}>Submit support request</Button>
  </form></details>
}

function Conversation({ base, id, back }: { base: string; id: number; back: () => void }) {
  const [page, setPage] = useState(0); const [body, setBody] = useState(''); const [status, setStatus] = useState('OPEN')
  const [saved, setSaved] = useState(''); const attempt = useRef<{ body: string; key: string } | null>(null)
  const mutation = useMutation()
  const resource = useResource(() => request<Detail>(`${base}/${id}?limit=20&offset=${page * 20}`, { cache: 'no-store' }), `support-detail:${base}:${id}:${page}`)
  return <section className="fg-stack"><Button variant="secondary" disabled={mutation.pending} onClick={back}>Back to requests</Button>
    {resource.loading ? <Skeleton cards={1} /> : resource.error ? <ErrorState message={resource.error} retry={resource.retry} /> : resource.data && <>
      <h2 style={{ overflowWrap: 'anywhere' }}>Request #{id}: {resource.data.subject}</h2><p>{resource.data.status} · Revision {resource.data.version}</p>
      <Button variant="secondary" disabled={mutation.pending} onClick={resource.retry}>Refresh conversation</Button>
      {resource.data.messages.map(message => <article key={message.id} className="fg-panel"><strong>{message.author_kind === 'ADMIN' ? 'Administrator' : 'Requester'}</strong><p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{message.body}</p><small>{istDateTime(message.created_at)}</small></article>)}
      <div className="fg-actions"><Button disabled={page === 0 || mutation.pending} onClick={() => setPage(p => p - 1)}>Earlier messages</Button><span>Page {page + 1}</span><Button disabled={(page + 1) * 20 >= resource.data.message_total || mutation.pending} onClick={() => setPage(p => p + 1)}>Later messages</Button></div>
      {resource.data.can_reply ? <form className="fg-stack" onSubmit={e => {
        e.preventDefault(); const text = body.trim(); setSaved('')
        if (!attempt.current || attempt.current.body !== text) attempt.current = { body: text, key: crypto.randomUUID() }
        const current = attempt.current; const version = resource.data!.version
        void mutation.run(async () => { await request(`${base}/${id}/messages`, { method: 'POST', headers: { 'Idempotency-Key': current.key }, body: JSON.stringify({ body: current.body, expected_version: version }) }); setBody(''); attempt.current = null; setSaved('Reply saved.'); resource.retry() })
      }}><label className="fg-field">Reply<textarea value={body} onChange={e => setBody(e.target.value)} rows={5} required maxLength={2000} disabled={mutation.pending} /></label><Button type="submit" loading={mutation.pending}>Send reply</Button></form> : <p>This request is resolved. An administrator must reopen it before further replies.</p>}
      {resource.data.can_change_status && <div className="fg-stack"><label className="fg-field">New status<select value={status} onChange={e => setStatus(e.target.value)} disabled={mutation.pending}>{statuses.map(s => <option key={s}>{s}</option>)}</select></label><Button variant="secondary" loading={mutation.pending} disabled={status === resource.data.status} onClick={() => { setSaved(''); void mutation.run(async () => { await request(`${base}/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status, expected_version: resource.data!.version }) }); setSaved('Status updated.'); resource.retry() }) }}>Update request status</Button></div>}
    </>}{mutation.error && <Alert>{mutation.error} Refresh the conversation if another participant changed it. Your draft is retained.</Alert>}{saved && <p role="status">{saved}</p>}
  </section>
}