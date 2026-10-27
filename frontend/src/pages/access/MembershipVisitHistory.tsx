import { useState } from 'react'
import { useResource } from '../../hooks/useResource'
import { request, localDate } from '../../services/client'
import { istDateTime } from '../../utils/membership'
import { Button, EmptyState, ErrorState, Heading, Link, Skeleton } from '../../components/common/UI'

type Visit = { id: number; gym_id: number; gym_name: string; membership_id: number; checkin_time: string }
export default function MembershipVisitHistory() {
  const [month, setMonth] = useState(localDate().slice(0, 7)), [page, setPage] = useState(0)
  const [year, number] = month.split('-').map(Number)
  const data = useResource(() => request<{ total: number; items: Visit[] }>(`/profile/membership-visits?year=${year}&month=${number}&limit=20&offset=${page * 20}`, { cache: 'no-store' }), `membership-visits:${month}:${page}`)
  return <div className="fg-narrow fg-stack"><Heading title="Membership visit history" subtitle="Successful check-ins using your Single-Gym or FitiGo Multi-Gym membership. Individual bookings are shown in My bookings." /><Link to="/bookings">My bookings</Link><label className="fg-field">Month<input type="month" min="2000-01" max="2100-12" value={month} onChange={e => { if (e.target.value) { setMonth(e.target.value); setPage(0) } }} /></label>{data.loading ? <Skeleton cards={2} /> : data.error ? <ErrorState message={data.error} retry={data.retry} /> : data.data?.items.length ? data.data.items.map(visit => <article key={visit.id} className="fg-panel fg-stack"><h2>{visit.gym_name}</h2><p>{istDateTime(visit.checkin_time)} · Verified membership entry</p><Link to={`/membership/${visit.membership_id}`}>Membership #{visit.membership_id}</Link><Link to={`/gyms/${visit.gym_id}`}>View gym</Link></article>) : <EmptyState title="No membership visits this month" description="Your successful membership check-ins will appear here. Try another month to see earlier visits." />}<div className="fg-row"><Button variant="secondary" disabled={page === 0} onClick={() => setPage(p => p - 1)}>Previous</Button><span>Page {page + 1} · {data.data?.total || 0} visits</span><Button variant="secondary" disabled={!data.data || (page + 1) * 20 >= data.data.total} onClick={() => setPage(p => p + 1)}>Next</Button></div><Link to="/profile">Back to profile</Link></div>
}