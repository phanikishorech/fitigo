import { useState } from 'react'
import { fetchAdminDashboardSummary, fetchAdminGyms, fetchAdminBookings } from '../screens/Admin/api'
import { dateLabel, localDate, money } from '../services/client'
import { dashboardService } from './services'
import { useAdminResource } from './hooks'
import { DataCard, EmptyState, Icon, Identity, Link, MetricCard, PageHeader, Resource, StatusBadge, personName } from './UI'
import DateRangePicker, { dateRangeLabel } from '../components/common/DateRangePicker'
import { presetRange, rangeDays, type DateRange } from '../utils/dateRange'

export function BookingActivity({ range }: { range: DateRange }) {
  const days = rangeDays(range)
  const activity = useAdminResource(() => dashboardService.daily({ ...range, limit: days }), `activity:${range.date_from}:${range.date_to}`)
  return <DataCard title="Booking activity"><p className="ad-card-subtitle">Bookings by scheduled date · {dateRangeLabel(range)}</p><Resource resource={activity}>{rows => {
    if (!rows.length) return <EmptyState title="No booking activity in this period." description="Booking activity will appear here as the platform grows." />
    const sorted = [...rows].sort((a, b) => a.day.localeCompare(b.day)); const max = Math.max(1, ...rows.map(row => row.total_bookings))
    return <><div className="ad-chart" role="img" aria-label={`Booking activity for ${days} days. Exact values are available in the data table below.`}>{sorted.map(row => <div className="ad-chart-column" key={row.day}><div className="ad-chart-track"><div className="ad-chart-bar" style={{ height: `${Math.max(2, row.total_bookings / max * 100)}%` }} title={`${dateLabel(row.day)}: ${row.total_bookings} bookings`}><span>{row.total_bookings}</span></div></div><small>{row.day.slice(8)}</small></div>)}</div><details className="ad-chart-data"><summary>View chart data</summary><table><caption>Booking activity</caption><thead><tr><th scope="col">Date</th><th scope="col">Bookings</th></tr></thead><tbody>{sorted.map(row => <tr key={row.day}><td>{dateLabel(row.day)}</td><td>{row.total_bookings}</td></tr>)}</tbody></table></details></>
  }}</Resource></DataCard>
}
export default function Dashboard() {
  const [range, setRange] = useState(() => presetRange('today', localDate()))
  const key = `${range.date_from}:${range.date_to}`
  const summary = useAdminResource(() => fetchAdminDashboardSummary(range), `dashboard-summary:${key}`)
  const pending = useAdminResource(() => fetchAdminGyms({ status: 'PENDING_APPROVAL', limit: 4 }), 'dashboard-pending')
  const bookings = useAdminResource(() => fetchAdminBookings({ ...range, limit: 5 }), `dashboard-bookings:${key}`)
  return <>
    <PageHeader title="Dashboard" subtitle="Platform overview and activity" />
    <DateRangePicker value={range} onChange={setRange} />
    <Resource resource={summary}>{data => <>
      <div className="ad-metrics">
        <MetricCard title="New users" value={data.users.in_period.toLocaleString()} caption="Registered in selected range" icon="user" />
        <MetricCard title="New gyms" value={data.gyms.in_period.toLocaleString()} caption="Created in selected range" icon="gym" />
        <MetricCard title="Bookings in range" value={data.bookings.in_period.toLocaleString()} caption={`${data.bookings.confirmed_in_period} confirmed · scheduled in range`} icon="ticket" />
        <MetricCard title="Booking revenue" value={money(data.revenue.in_period, data.revenue.currency)} caption="Paid bookings · scheduled in range" icon="wallet" />
      </div>
      <p className="ad-card-subtitle">All-time totals — Total users: {data.users.total.toLocaleString()} · Total gyms: {data.gyms.total.toLocaleString()} · Currently awaiting approval: {data.gyms.pending_approval}. These totals and the approval queue are not date-filtered.</p>
    </>}</Resource>
    <div className="ad-operational-grid">
      <DataCard title="Pending gym approvals" action={<Link to="/admin/gyms?status=PENDING_APPROVAL" className="ad-text-link">View all<Icon name="arrow" size={16} /></Link>}>
        <p className="ad-card-subtitle">Current review queue · all dates</p>
        <Resource resource={pending}>{gyms => gyms.length ? <div className="ad-pending-list">{gyms.map(gym => <article key={gym.id}><Identity icon="gym" name={gym.name} caption={`${gym.city || 'Location not provided'} · Owner #${gym.owner_user_id}`} /><div className="ad-pending-meta"><small>Created {dateLabel(gym.created_at)}</small><StatusBadge status={gym.status} /></div><Link className="fg-button fg-button--secondary" to={`/admin/gyms/${gym.id}/review`}>Review<Icon name="chevron" size={15} /></Link></article>)}</div> : <EmptyState title="No gyms are waiting for approval." description="You’re all caught up." />}</Resource>
      </DataCard>
      <DataCard title="Recent bookings" action={<Link to={`/admin/bookings?${new URLSearchParams(range)}`} className="ad-text-link">View all<Icon name="arrow" size={16} /></Link>}>
        <p className="ad-card-subtitle">Latest reservations scheduled in the selected range</p>
        <Resource resource={bookings}>{rows => rows.length ? <div className="ad-recent-list">{rows.map(booking => <Link key={booking.id} to={`/admin/bookings/${booking.id}`} className="ad-recent-booking"><div><strong>#{booking.id} <span>{personName(booking.customer)}</span></strong><small>{booking.gym.name} · {dateLabel(booking.slot_date)}</small><StatusBadge status={booking.status} /></div><div><strong>{money(booking.total_price, booking.currency)}</strong>{booking.payment ? <StatusBadge status={booking.payment.status} /> : <small>No payment record</small>}</div></Link>)}</div> : <EmptyState title="No bookings found." description="No bookings are scheduled in this date range." />}</Resource>
      </DataCard>
    </div>
    <BookingActivity range={range} />
    <section className="ad-quick-section"><h2>Quick actions</h2><div className="ad-quick-actions">{[{ to: '/admin/gyms?status=PENDING_APPROVAL', title: 'Review gym approvals', text: 'Welcome new partners to FitiGo', icon: 'gym' as const }, { to: '/admin/users', title: 'Manage users', text: 'View accounts and platform access', icon: 'user' as const }, { to: '/admin/bookings', title: 'Manage bookings', text: 'Review reservations and payments', icon: 'ticket' as const }].map(action => <Link key={action.to} to={action.to}><span className="ad-icon-tile"><Icon name={action.icon} /></span><span><strong>{action.title}</strong><small>{action.text}</small></span><Icon name="arrow" size={18} /></Link>)}</div></section>
  </>
}