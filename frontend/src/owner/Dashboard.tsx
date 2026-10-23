import { useState } from 'react'
import { fetchGymDetailsOwner, fetchOwnerSummary, listBookings, listOwnerAttendance, type OwnerDashboardSummary } from '../screens/GymOwner/api'
import { useResource } from '../hooks/useResource'
import { useOwner } from './context'
import { Card, EmptyState, ErrorState, Link, MetricCard, PageHeader, Skeleton, StatusBadge } from './UI'
import { localDate, money } from '../services/client'
import Icon from '../components/common/Icon'
import { Image } from '../components/common/UI'
import { istDateTime } from '../utils/membership'
import DateRangePicker, { dateRangeLabel } from '../components/common/DateRangePicker'
import { presetRange, type DateRange } from '../utils/dateRange'
import { BookingTable } from './Bookings'

function PeriodBookings({ gymId, range }: { gymId: number; range: DateRange }) {
  const resource = useResource(() => listBookings(gymId, { ...range, limit: 6 }), `dashboard-bookings:${gymId}:${range.date_from}:${range.date_to}`)
  return <Card title="Bookings in selected range" action={<Link to={`/owner/bookings?${new URLSearchParams(range)}`} className="ow-text-link">View all <Icon name="arrow" size={15} /></Link>}>{resource.loading ? <Skeleton cards={2} /> : resource.error ? <ErrorState message={resource.error} retry={resource.retry} /> : resource.data?.length ? <BookingTable bookings={resource.data} compact={range.date_from === range.date_to} /> : <EmptyState title="No bookings yet" description="No bookings for this gym in the selected date range." />}</Card>
}
function RecentAttendance({ gymId, range }: { gymId: number; range: DateRange }) {
  const resource = useResource(() => listOwnerAttendance(gymId, range), `dashboard-attendance:${gymId}:${range.date_from}:${range.date_to}`)
  const labels = { fitigo_member: 'FitiGo member', single_gym_membership: 'Single-gym membership', individual_booking: 'Individual booking' }
  return <Card title="Recorded attendance" action={<Icon name="check" />}>
    <p className="ow-caption">Latest attendance · selected gym · {dateRangeLabel(range)}</p>
    {resource.loading ? <Skeleton cards={1} /> : resource.error ? <ErrorState message={resource.error} retry={resource.retry} /> : resource.data?.length ? <div className="ow-activity">{resource.data.map(record => {
      const content = <><span className="ow-avatar">{record.customer_name[0]}</span><span><strong>{record.customer_name}</strong><small>{labels[record.category]}{record.visits > 1 ? ` · ${record.visits} visitors` : ''}</small></span><span><StatusBadge status="ATTENDED" /><small>{record.recorded_at ? istDateTime(record.recorded_at) : 'Time unavailable'}</small></span></>
      return record.booking_id ? <Link to={`/owner/bookings/${record.booking_id}`} key={record.id}>{content}</Link> : <div className="ow-attendance-row" key={record.id}>{content}</div>
    })}</div> : <EmptyState title="No recorded attendance" description="No membership check-ins or booking attendance for this gym in the selected range." />}
  </Card>
}

function VisitMetrics({ visits, scope }: { visits: OwnerDashboardSummary['visits']; scope: string }) {
  return <div className="ow-metric-grid">
    <MetricCard icon="ticket" label="FitiGo member visits" value={visits.fitigo_member} note={scope} />
    <MetricCard icon="gym" label="Single-gym membership visits" value={visits.single_gym_membership} note={scope} />
    <MetricCard icon="calendar" label="Individual booking visits" value={visits.individual_booking} note={scope} />
    <MetricCard icon="check" label="Total visits" value={visits.total} note="FitiGo + single-gym + individual booking visits" />
  </div>
}

function SelectedGymMetrics({ gymId, range }: { gymId: number; range: DateRange }) {
  const summary = useResource(() => fetchOwnerSummary({ gymId, ...range }), `gym-dashboard:${gymId}:${range.date_from}:${range.date_to}`)
  if (summary.loading) return <Skeleton cards={4} />
  if (summary.error) return <Card><ErrorState message={summary.error} retry={summary.retry} /></Card>
  if (!summary.data) return null
  return <>
    <VisitMetrics visits={summary.data.visits} scope="Selected gym · selected range" />
    <div className="ow-metric-grid">
      <MetricCard icon="calendar" label="Bookings in range" value={summary.data.bookings.in_period} note="Selected gym · scheduled in range" />
      <MetricCard icon="clock" label="Confirmed bookings" value={summary.data.bookings.confirmed_in_period} note="Selected gym · scheduled in range" />
      <MetricCard icon="wallet" label="Booking revenue" value={money(summary.data.revenue.in_period, summary.data.revenue.currency)} note="Paid bookings · scheduled in range" />
    </div>
  </>
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
  const [range, setRange] = useState(() => presetRange('today', localDate()))
  const summary = useResource(() => fetchOwnerSummary(range), `owner-summary:${range.date_from}:${range.date_to}`)
  const hour = Number(new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', hour: '2-digit', hourCycle: 'h23' }).format(new Date())); const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
  return <div className="ow-stack ow-stack-lg"><PageHeader eyebrow="YOUR DAILY OVERVIEW" title={`${greeting}${user.first_name ? `, ${user.first_name}` : ''}`} description="A little clarity for a stronger day. Here's your business at a glance." action={<Link to="/owner/check-in" className="fg-button fg-button--primary"><Icon name="qr" />Scan member QR</Link>} />
    <DateRangePicker value={range} onChange={setRange} />
    <div className="ow-section-label"><span><span className="ow-live-dot" />Overall metrics <small>All your gyms · {dateRangeLabel(range)}</small></span></div>
    {summary.loading ? <Skeleton cards={4} /> : summary.error ? <Card><ErrorState message={summary.error} retry={summary.retry} /></Card> : summary.data && <VisitMetrics visits={summary.data.visits} scope="All your gyms · selected range" />}
    {!gymId ? <Card><EmptyState title="Your next chapter starts here" description="Create your first gym and submit it for approval." action={<Link className="fg-button fg-button--primary" to="/owner/gyms/create"><Icon name="plus" />Add your first gym</Link>} /></Card> : <>
      <div className="ow-section-label"><span><Icon name="gym" size={18} /><strong>{gym?.name}</strong><small>Selected gym metrics · {dateRangeLabel(range)}</small></span></div>
      <SelectedGymMetrics gymId={gymId} range={range} />
      <div className="ow-dashboard-grid"><PeriodBookings gymId={gymId} range={range} /><RecentAttendance gymId={gymId} range={range} /></div>
      <div className="ow-dashboard-grid"><GymSummary gymId={gymId} /><Card title="Quick actions"><div className="ow-quick-actions">{[{ to: '/owner/check-in', icon: 'qr' as const, title: 'Scan member QR', note: 'Validate access at the door' }, { to: `/owner/gyms/${gymId}/classes`, icon: 'clock' as const, title: 'Manage classes & slots', note: 'Schedules, pricing and capacity' }, { to: `/owner/gyms/${gymId}/memberships`, icon: 'ticket' as const, title: 'Membership plans', note: 'Keep your offerings up to date' }, { to: '/owner/staff', icon: 'shield' as const, title: 'Manage your team', note: 'Staff access and assignments' }].map(a => <Link to={a.to} key={a.to}><span className="ow-icon-tile"><Icon name={a.icon} /></span><span><strong>{a.title}</strong><small>{a.note}</small></span><Icon name="chevron" size={17} /></Link>)}</div></Card></div>
    </>}
  </div>
}