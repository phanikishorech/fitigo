import { useState } from 'react'
import { fetchGymDetailsOwner, fetchOwnerSummary, listBookings } from '../screens/GymOwner/api'
import { useResource } from '../hooks/useResource'
import { useOwner } from './context'
import { Card, EmptyState, ErrorState, Input, Link, MetricCard, PageHeader, Skeleton, StatusBadge, Unavailable } from './UI'
import { localDate, money } from '../services/client'
import Icon from '../components/common/Icon'
import { Image } from '../components/common/UI'
import { capabilities, customerName } from './services'
import { BookingTable } from './Bookings'

function TodayBookings({ gymId, date }: { gymId: number; date: string }) {
  const resource = useResource(() => listBookings(gymId, { date, limit: 6 }), `dashboard-bookings:${gymId}:${date}`)
  return <Card title={date === localDate() ? "Today's bookings" : 'Bookings'} action={<Link to={`/owner/bookings?date=${date}`} className="ow-text-link">View all <Icon name="arrow" size={15} /></Link>}>{resource.loading ? <Skeleton cards={2} /> : resource.error ? <ErrorState message={resource.error} retry={resource.retry} /> : resource.data?.length ? <BookingTable bookings={resource.data} compact /> : <EmptyState title="No bookings yet" description="New bookings for this date will appear here." />}</Card>
}
function RecentAttendance({ gymId, date }: { gymId: number; date: string }) {
  const resource = useResource(() => listBookings(gymId, { date, limit: 50 }), `dashboard-attendance:${gymId}:${date}`)
  const attended = resource.data?.filter(b => b.attendance_status === 'ATTENDED').sort((a, b) => (b.attendance_marked_at || '').localeCompare(a.attendance_marked_at || '')).slice(0, 4)
  return <Card title="Recorded attendance" action={<Icon name="check" />}><p className="ow-caption">From the latest 50 bookings for this date</p>{resource.loading ? <Skeleton cards={1} /> : resource.error ? <ErrorState message={resource.error} retry={resource.retry} /> : attended?.length ? <div className="ow-activity">{attended.map(b => <Link to={`/owner/bookings/${b.id}`} key={b.id}><span className="ow-avatar">{customerName(b.customer)[0]}</span><span><strong>{customerName(b.customer)}</strong><small>{b.slot.name}</small></span><span><StatusBadge status="ATTENDED" /><small>{b.attendance_marked_at ? new Date(b.attendance_marked_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Time unavailable'}</small></span></Link>)}</div> : <EmptyState title="No recorded attendance" description="Attendance returned by the booking API will appear here." />}<p className="ow-caption ow-card-footnote">{capabilities.checkins.message}</p></Card>
}
function GymSummary({ gymId }: { gymId: number }) {
  const resource = useResource(() => fetchGymDetailsOwner(gymId), `gym-summary:${gymId}`)
  if (resource.loading) return <Card><Skeleton cards={1} /></Card>
  if (resource.error) return <Card><ErrorState message={resource.error} retry={resource.retry} /></Card>
  const gym = resource.data!
  const cover = gym.images.find(i => i.is_cover) || gym.images[0]
  const hour = gym.operating_hours.find(h => h.day_of_week === (new Date().getDay() + 6) % 7)
  return <Card title="Your gym" action={<Link className="ow-text-link" to={`/owner/gyms/${gymId}`}>Manage gym <Icon name="arrow" size={15} /></Link>}><div className="ow-gym-summary"><Image src={cover ? `/uploads/${cover.file_path}` : null} alt={gym.name} /><div><StatusBadge status={gym.status === 'APPROVED' && !gym.is_active ? 'INACTIVE' : gym.status} /><h3>{gym.name}</h3><p><Icon name="pin" size={16} />{[gym.address_line_1, gym.city].filter(Boolean).join(', ') || 'Location not configured'}</p><p><Icon name="clock" size={16} />{hour ? hour.is_closed ? 'Closed today' : `${hour.open_time?.slice(0, 5) || '—'} – ${hour.close_time?.slice(0, 5) || '—'}` : 'Hours not configured'}</p>{gym.status === 'APPROVED' && gym.is_active && <Link className="ow-text-link" to={`/gyms/${gym.id}`}>View on FitiGo <Icon name="arrow" size={15} /></Link>}</div></div></Card>
}
export default function Dashboard() {
  const { user, gymId, gym } = useOwner()
  const [date, setDate] = useState(localDate())
  const summary = useResource(fetchOwnerSummary, 'owner-summary')
  const hour = new Date().getHours(); const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
  return <div className="ow-stack ow-stack-lg"><PageHeader eyebrow="YOUR DAILY OVERVIEW" title={`${greeting}${user.first_name ? `, ${user.first_name}` : ''}`} description="A little clarity for a stronger day. Here's your business at a glance." action={<Link to="/owner/check-in" className="fg-button fg-button--primary"><Icon name="qr" />Scan member QR</Link>} />
    <div className="ow-section-label"><span><span className="ow-live-dot" />Portfolio overview <small>All your gyms · today</small></span><Link to="/owner/analytics" className="ow-text-link">View overview <Icon name="arrow" size={15} /></Link></div>
    {summary.loading ? <Skeleton cards={4} /> : summary.error ? <Card><ErrorState message={summary.error} retry={summary.retry} /></Card> : summary.data && <div className="ow-metric-grid"><MetricCard icon="calendar" label="Today's bookings" value={summary.data.bookings.today} note="Across all your gyms" /><MetricCard icon="clock" label="Upcoming bookings" value={summary.data.bookings.upcoming} note="Includes today's upcoming activity" /><MetricCard icon="wallet" label="Booking revenue" value={money(summary.data.revenue.last_30d, summary.data.revenue.currency)} note="Last 30 days · all gyms" /><MetricCard icon="gym" label="Approved gyms" value={summary.data.gyms.approved} note={`${summary.data.gyms.total} gyms in your portfolio`} /></div>}
    {!gymId ? <Card><EmptyState title="Your next chapter starts here" description="Create your first gym and submit it for approval." action={<Link className="fg-button fg-button--primary" to="/owner/gyms/create"><Icon name="plus" />Add your first gym</Link>} /></Card> : <><div className="ow-section-label"><span><Icon name="gym" size={18} /><strong>{gym?.name}</strong><small>Gym operations</small></span><Input label="Booking date" type="date" value={date} onChange={e => e.target.value && setDate(e.target.value)} /></div><div className="ow-dashboard-grid"><TodayBookings gymId={gymId} date={date} /><RecentAttendance gymId={gymId} date={date} /></div><div className="ow-dashboard-grid"><GymSummary gymId={gymId} /><Card title="Quick actions"><div className="ow-quick-actions">{[{ to: '/owner/check-in', icon: 'qr' as const, title: 'Scan member QR', note: 'Validate access at the door' }, { to: `/owner/gyms/${gymId}/classes`, icon: 'clock' as const, title: 'Manage classes & slots', note: 'Schedules, pricing and capacity' }, { to: `/owner/gyms/${gymId}/memberships`, icon: 'ticket' as const, title: 'Membership plans', note: 'Keep your offerings up to date' }, { to: '/owner/staff', icon: 'shield' as const, title: 'Manage your team', note: 'Staff access and assignments' }].map(a => <Link to={a.to} key={a.to}><span className="ow-icon-tile"><Icon name={a.icon} /></span><span><strong>{a.title}</strong><small>{a.note}</small></span><Icon name="chevron" size={17} /></Link>)}</div></Card></div></>}
  </div>
}