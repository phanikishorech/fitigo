import { useId, useState } from 'react'
import { fetchOwnerSummary, type OwnerDashboardSummary } from '../screens/GymOwner/api'
import { useOwnerReport } from './useOwnerReport'
import { useOwner } from './context'
import { Button, Card, EmptyState, ErrorState, Link, PageHeader, Skeleton } from './UI'
import { localDate, money } from '../services/client'
import Icon from '../components/common/Icon'
import DateRangePicker, { dateRangeLabel } from '../components/common/DateRangePicker'
import { presetRange, type DateRange } from '../utils/dateRange'
import { PrimaryMetrics } from './ReportMetrics'

function SummarySection({ title, description, range, gymId }: { title: string; description: string; range: DateRange; gymId?: number }) {
  const [expanded, setExpanded] = useState(false)
  const id = useId()
  const resource = useOwnerReport(() => fetchOwnerSummary({ ...range, gymId }), `compact-summary:${gymId || 'all'}:${range.date_from}:${range.date_to}`)
  const destination = `/owner/analytics?${new URLSearchParams({ ...range, gym_id: gymId ? String(gymId) : 'all' })}`
  const rows = (data: OwnerDashboardSummary) => [
    ['Multi-Gym member visits', data.visits.fitigo_member, 'visits'], ['Single-Gym member visits', data.visits.single_gym_membership, 'visits'],
    ['Individual booking visits', data.visits.individual_booking, 'visits'],
    ...(gymId ? [['Attended bookings', data.attendance.attended, 'bookings']] : []),
    ['Cancelled bookings', data.attendance.cancelled, 'bookings'], ['Not attended / no-show', data.attendance.no_show, 'bookings'],
    ['Single-Gym membership revenue', money(data.revenue.single_gym_membership), 'revenue'], ['Individual booking revenue', money(data.revenue.individual_booking), 'revenue']
  ]
  return <section className="ow-report-section ow-compact-summary" aria-label={title}>
    <header className="ow-report-heading"><div><h2>{title}</h2><p>{description} · {dateRangeLabel(range)}</p></div>
      <Button variant="text" aria-expanded={expanded} aria-controls={id} onClick={() => setExpanded(value => !value)}>{expanded ? 'Show fewer metrics' : 'View more metrics'}</Button>
    </header>
    {resource.loading ? <Skeleton cards={3} /> : resource.error ? <ErrorState message={resource.error} retry={resource.retry} /> : resource.data && <>
      <PrimaryMetrics data={resource.data} />
      <div id={id} hidden={!expanded} className="ow-secondary-panel"><dl className="ow-secondary-metrics">{rows(resource.data).map(([label, value, section]) => <div key={label}><dt><Link to={`${destination}#${section}`}>{label}</Link></dt><dd>{typeof value === 'number' ? value.toLocaleString('en-IN') : value}</dd></div>)}</dl><Link className="ow-text-link" to={destination}>Open Analytics & Reports <Icon name="arrow" size={15} /></Link></div>
    </>}
  </section>
}

export default function Dashboard() {
  const { user, gymId, gym } = useOwner()
  const [range, setRange] = useState(() => presetRange('today', localDate()))
  return <div className="ow-stack ow-stack-lg">
    <PageHeader eyebrow="YOUR DAILY OVERVIEW" title={`Welcome${user.first_name ? `, ${user.first_name}` : ''}`} description="Your business at a glance. Explore the details when you need them." action={<Link to="/owner/check-in" className="fg-button fg-button--primary"><Icon name="qr" />Scan member QR</Link>} />
    <DateRangePicker value={range} onChange={setRange} />
    <SummarySection title="Overall Metrics" description="All gyms owned by your account" range={range} />
    {gymId ? <SummarySection title="Selected Gym" description={gym?.name || 'Selected gym'} range={range} gymId={gymId} /> : <Card><EmptyState title="Add your first gym" action={<Link to="/owner/gyms/create">Create a gym</Link>} /></Card>}
    <div className="ow-dashboard-footer"><p className="ow-caption">Visits: check-in date. Upcoming: scheduled date. Revenue: purchase date. IST · refreshes every 30 seconds while visible.</p><Link to={`/owner/analytics?${new URLSearchParams({ ...range, gym_id: 'all' })}`} className="ow-text-link">Analytics & Reports <Icon name="arrow" size={16} /></Link></div>
  </div>
}