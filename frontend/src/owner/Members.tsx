import { useState } from 'react'
import { useOwner } from './context'
import { useResource } from '../hooks/useResource'
import { request, dateLabel } from '../services/client'
import { istDateTime } from '../utils/membership'
import { Button, Card, EmptyState, ErrorState, Input, Notice, PageHeader, Pagination, Skeleton, StatusBadge } from './UI'

type Member = { id: number; name: string; membership_status: string }
type History = { id: number; name: string; memberships: { id: number; status: string; start_at: string; end_at: string }[];
  bookings: { id: number; date: string; status: string; attendance_status: string | null; quantity: number }[];
  visits: { id: number; at: string; source: string; booking_id: number | null }[]; booking_total: number; visit_total: number }

export default function Members() {
  const { gymId } = useOwner(); const [search, setSearch] = useState(''); const [q, setQ] = useState(''); const [page, setPage] = useState(0); const [selected, setSelected] = useState<number | null>(null)
  const resource = useResource(() => gymId ? request<{ items: Member[]; total: number }>(`/gym-owner/gyms/${gymId}/members?q=${encodeURIComponent(q)}&limit=20&offset=${page * 20}`) : Promise.resolve({ items: [], total: 0 }), `members:${gymId}:${q}:${page}`)
  if (!gymId) return <EmptyState title="Select a gym" />
  if (selected) return <MemberHistory key={`${gymId}:${selected}`} gymId={gymId} id={selected} back={() => setSelected(null)} />
  return <div className="ow-stack"><PageHeader title="Members" description="Customers with memberships, bookings or successful visits at this gym." />
    <Notice>Only this gym's operational history is shown. Multi-Gym membership details, activity elsewhere, contact information and payment credentials are not exposed.</Notice>
    <Card><form className="ow-actions" onSubmit={e => { e.preventDefault(); setQ(search.trim()); setPage(0) }}><Input label="Search member name" value={search} maxLength={100} onChange={e => setSearch(e.target.value)} /><Button type="submit">Search</Button></form>
      {resource.loading ? <Skeleton /> : resource.error ? <ErrorState message={resource.error} retry={resource.retry} /> : <>
        {!resource.data?.items.length ? <EmptyState title="No members match" /> : <div className="ow-stack">{resource.data.items.map(member => <article key={member.id} className="ow-card"><h2>{member.name}</h2><StatusBadge status={member.membership_status} /><Button variant="secondary" onClick={() => setSelected(member.id)}>View gym history</Button></article>)}</div>}
        <Pagination page={page} hasMore={(page + 1) * 20 < (resource.data?.total || 0)} onChange={setPage} /></>}
    </Card></div>
}
function MemberHistory({ gymId, id, back }: { gymId: number; id: number; back: () => void }) {
  const [page, setPage] = useState(0)
  const resource = useResource(() => request<History>(`/gym-owner/gyms/${gymId}/members/${id}?limit=20&offset=${page * 20}`), `history:${gymId}:${id}:${page}`)
  return <div className="ow-stack"><Button variant="secondary" onClick={back}>Back to members</Button>{resource.loading ? <Skeleton /> : resource.error ? <ErrorState message={resource.error} retry={resource.retry} /> : resource.data && <>
    <PageHeader title={resource.data.name} description="History at the selected gym only. Manual attendance is not a verified visit." />
    <Card title="Gym memberships">{resource.data.memberships.length ? resource.data.memberships.map(m => <p key={m.id}><StatusBadge status={m.status} /> {dateLabel(m.start_at)} – {dateLabel(m.end_at)}</p>) : <EmptyState title="No membership sold by this gym" />}</Card>
    <Card title="Bookings">{resource.data.bookings.length ? resource.data.bookings.map(b => <p key={b.id}>#{b.id} · {dateLabel(b.date)} · {b.quantity} places · <StatusBadge status={b.status} /> {b.attendance_status && <StatusBadge status={b.attendance_status} />}</p>) : <EmptyState title="No bookings on this page" />}</Card>
    <Card title="Verified visits">{resource.data.visits.length ? resource.data.visits.map(v => <p key={v.id}>{istDateTime(v.at)} · {v.source.replaceAll('_', ' ')}{v.booking_id ? ` · Booking #${v.booking_id}` : ''}</p>) : <EmptyState title="No verified visits on this page" />}</Card>
    <Pagination page={page} hasMore={(page + 1) * 20 < Math.max(resource.data.booking_total, resource.data.visit_total)} onChange={setPage} />
  </>}</div>
}