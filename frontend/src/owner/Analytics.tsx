import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useOwner } from './context'
import { useOwnerReport } from './useOwnerReport'
import { analyticsService, type Scope, type Page } from './analyticsService'
import { categoryLabels, RevenueBasis } from './ReportMetrics'
import ReportChart from './ReportChart'
import { Button, Card, EmptyState, ErrorState, Field, Link, MetricCard, PageHeader, Pagination, Skeleton, StatusBadge } from './UI'
import { dateLabel, localDate, money } from '../services/client'
import { istDateTime } from '../utils/membership'
import DateRangePicker, { dateRangeLabel } from '../components/common/DateRangePicker'
import { presetRange, rangeError, type DateRange } from '../utils/dateRange'

function Results<T>({ resource, page, setPage, children }: { resource: { loading: boolean; error: string; data: Page<T> | null; retry: () => void }; page: number; setPage: (value: number) => void; children: (items: T[]) => ReactNode }) {
  if (resource.loading) return <Skeleton cards={1} />
  if (resource.error) return <ErrorState message={resource.error} retry={resource.retry} />
  return <>{resource.data?.items.length ? children(resource.data.items) : <EmptyState title="No matching records" description="Try another date, gym or record filter." />}<p className="ow-caption">{resource.data?.total || 0} records · 10 per page</p><Pagination page={page} hasMore={(page + 1) * 10 < (resource.data?.total || 0)} onChange={setPage} /></>
}

function BookingRecords({ scope, version }: { scope: Scope; version: number }) {
  const [page, setPage] = useState(0), [category, setCategory] = useState('')
  const data = useOwnerReport(() => analyticsService.bookings(scope, page, category), `analytics-bookings:${JSON.stringify(scope)}:${page}:${category}:${version}`)
  return <Card title="Booking records"><Field label="Booking outcome"><select value={category} onChange={e => { setCategory(e.target.value); setPage(0) }}><option value="">All outcomes</option>{['upcoming', 'attended', 'cancelled', 'no_show', 'pending_payment', 'expired', 'unresolved'].map(key => <option key={key} value={key}>{categoryLabels[key]}</option>)}</select></Field>
    <Results resource={data} page={page} setPage={setPage}>{rows => <div className="ow-report-table" tabIndex={0} role="region" aria-label="Booking records"><table className="ow-table"><thead><tr><th>Date / time</th><th>Customer / visitors</th><th>Gym / slot / access</th><th>Amount</th><th>Booking / payment</th><th>Attendance</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td><Link to={`/owner/bookings/${row.id}`}>#{row.id} · {dateLabel(row.date)}</Link><small>{row.start_time.slice(0, 5)} IST</small></td><td><strong>{row.customer}</strong><small>{row.visitors.join(', ') || `${row.quantity} reserved places`}</small></td><td><strong>{row.gym_name}</strong><small>{row.slot_name} · {row.access_source.replaceAll('_', ' ')}</small></td><td>{money(row.amount, row.currency)}</td><td><StatusBadge status={row.status} /><small>{row.payment_status || 'No payment record'}</small></td><td>{categoryLabels[row.category]}{row.attendance_status && <small>Manual/scanner flag: {row.attendance_status}</small>}</td></tr>)}</tbody></table></div>}</Results>
  </Card>
}
function AttendanceRecords({ scope, version }: { scope: Scope; version: number }) {
  const [page, setPage] = useState(0)
  const data = useOwnerReport(() => analyticsService.attendance(scope, page), `analytics-attendance:${JSON.stringify(scope)}:${page}:${version}`)
  return <Card title="Successful attendance"><Results resource={data} page={page} setPage={setPage}>{rows => <div className="ow-report-table" tabIndex={0} role="region" aria-label="Successful attendance"><table className="ow-table"><thead><tr><th>Check-in (IST)</th><th>Visitor</th><th>Gym</th><th>Access</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{istDateTime(row.recorded_at)}</td><td>{row.booking_id ? <Link to={`/owner/bookings/${row.booking_id}`}>{row.customer}</Link> : row.customer}</td><td>{row.gym_name}</td><td>{categoryLabels[row.category]}</td></tr>)}</tbody></table></div>}</Results></Card>
}
function Transactions({ scope, version }: { scope: Scope; version: number }) {
  const [page, setPage] = useState(0), [category, setCategory] = useState(''), [status, setStatus] = useState('')
  const data = useOwnerReport(() => analyticsService.transactions(scope, page, category, status), `analytics-transactions:${JSON.stringify(scope)}:${page}:${category}:${status}:${version}`)
  return <Card title="Payment records"><div className="ow-analytics-filters"><Field label="Sale category"><select value={category} onChange={e => { setCategory(e.target.value); setPage(0) }}><option value="">All sales</option>{['single_gym_membership', 'individual_booking'].map(key => <option key={key} value={key}>{categoryLabels[key]}</option>)}</select></Field><Field label="Payment status"><select value={status} onChange={e => { setStatus(e.target.value); setPage(0) }}><option value="">All payment statuses</option>{['PAID', 'INITIATED', 'PENDING', 'FAILED', 'REFUNDED', 'PARTIALLY_REFUNDED', 'REVIEW_REQUIRED'].map(key => <option key={key}>{key}</option>)}</select></Field></div>
    <p className="ow-caption">Original sale amount and recognized revenue are separate. Excluded payments remain visible; this is not a refund-date or settlement ledger.</p>
    <Results resource={data} page={page} setPage={setPage}>{rows => <div className="ow-report-table" tabIndex={0} role="region" aria-label="Payment records"><table className="ow-table"><thead><tr><th>Purchase date</th><th>Gym / sale</th><th>Provider</th><th>Payment / checkout</th><th>Sale amount</th><th>Recognized revenue</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{istDateTime(row.recorded_at)}<small>{row.booking_id ? <Link to={`/owner/bookings/${row.booking_id}`}>Booking #{row.booking_id}</Link> : `Membership #${row.record_id}`}</small></td><td>{row.gym_name}<small>{categoryLabels[row.category]}</small></td><td>{row.provider}<small>{row.mode || 'Legacy'} · {row.transaction_id || 'No verified transaction'}</small></td><td><StatusBadge status={row.payment_status} /><small>{row.checkout_status || 'Unlinked record'}</small></td><td>{money(row.amount)}</td><td>{money(row.recognized_amount)}<small>{row.included ? 'Included' : row.exclusion_reason === 'NO_ELIGIBLE_CHECKIN' ? 'No eligible successful check-in' : 'Excluded by payment rules'}</small></td></tr>)}</tbody></table></div>}</Results>
  </Card>
}

export default function Analytics({ revenueOnly = false }: { revenueOnly?: boolean }) {
  const { gyms, gymId } = useOwner()
  const params = new URLSearchParams(location.search)
  const [selected, setSelected] = useState(() => params.get('gym_id') || 'all')
  const [range, setRange] = useState<DateRange>(() => {
    const candidate = { date_from: params.get('date_from') || '', date_to: params.get('date_to') || '' }
    return rangeError(candidate) ? presetRange('today', localDate()) : candidate
  })
  const [version, setVersion] = useState(0)
  const previousGym = useRef(gymId)
  useEffect(() => { if (previousGym.current !== gymId) { previousGym.current = gymId; setSelected(gymId ? String(gymId) : 'all') } }, [gymId])
  const scope: Scope = { ...range, ...(selected !== 'all' ? { gym_id: Number(selected) } : {}) }
  const scopeKey = JSON.stringify(scope)
  const resource = useOwnerReport(() => analyticsService.overview(scope), `analytics:${scopeKey}:${version}`)
  const jumped = useRef(false)
  useEffect(() => { if (resource.data && !jumped.current) { jumped.current = true; const id = location.hash.slice(1); if (['visits', 'bookings', 'revenue'].includes(id)) document.getElementById(id)?.scrollIntoView() } }, [resource.data])
  const data = resource.data, summary = data?.summary
  const scopeName = selected === 'all' ? 'All gyms owned by your account' : gyms.find(gym => String(gym.id) === selected)?.name || 'Selected gym'
  return <div className="ow-stack ow-stack-lg ow-analytics">
    <PageHeader title={revenueOnly ? 'Revenue Reports' : 'Analytics & Reports'} description="Real check-ins, booking outcomes and verified paid sales. One reporting scope throughout." action={<Link to="/owner/check-in" className="fg-button fg-button--primary">Scan member QR</Link>} />
    <div className="ow-analytics-filters"><Field label="Reporting gym"><select aria-label="Reporting gym" value={selected} onChange={e => setSelected(e.target.value)}><option value="all">All Gyms</option>{gyms.map(gym => <option key={gym.id} value={gym.id}>{gym.name}</option>)}</select></Field><Button variant="secondary" loading={resource.loading} onClick={() => setVersion(value => value + 1)}>Refresh reports</Button></div>
    <DateRangePicker value={range} onChange={setRange} />
    <p className="ow-caption">{scopeName} · {dateRangeLabel(range)} · updates every 30 seconds while visible.{summary && ` Updated ${istDateTime(summary.generated_at)}.`}</p>
    {resource.loading ? <Skeleton cards={3} /> : resource.error ? <ErrorState message={resource.error} retry={resource.retry} /> : data && summary && <>
      {!revenueOnly && <><section id="visits" className="ow-report-section"><h2>Visits overview</h2><div className="ow-metric-grid">
        <MetricCard icon="check" label="Total completed visits" value={summary.visits.total} emphasis note="Successful check-ins only" />
        <MetricCard icon="ticket" label="Multi-Gym member visits" value={summary.visits.fitigo_member} note="Check-in date" />
        <MetricCard icon="gym" label="Single-Gym member visits" value={summary.visits.single_gym_membership} note="Check-in date" />
        <MetricCard icon="calendar" label="Individual booking visits" value={summary.visits.individual_booking} note="One per checked-in visitor" />
        <MetricCard icon="clock" label="Upcoming visits" value={summary.upcoming_visits} note="Paid future visitor places; no check-in" />
      </div><Card title="Visits Over Time"><p className="ow-caption">{data.grouping} successful check-ins · IST</p><ReportChart points={data.series} metric="visits" title="Visits Over Time" /></Card></section>
      <section id="bookings" className="ow-report-section"><h2>Bookings and attendance</h2><div className="ow-metric-grid">{(['upcoming', 'attended', 'cancelled', 'no_show'] as const).map(key => <MetricCard key={key} icon="calendar" label={categoryLabels[key]} value={summary.attendance[key]} note="Bookings by scheduled visit date" />)}</div>
        <Card title="Booking outcomes"><p className="ow-caption">Mutually exclusive categories. Attended requires a successful check-in; a group booking counts once. Upcoming bookings include open windows, while upcoming visits include only future paid visitor places. Unmarked past bookings stay unresolved.</p><div className="ow-outcomes">{Object.entries(summary.attendance).map(([key, value]) => <div key={key}><span>{categoryLabels[key]}</span><meter min={0} max={Math.max(1, summary.bookings.in_period)} value={value} aria-label={categoryLabels[key]} /><strong>{value}</strong></div>)}</div></Card>
      </section></>}
      <section id="revenue" className="ow-report-section"><h2>Revenue analytics</h2><p className="ow-caption">{summary.revenue.mode === 'test' ? 'Test mode ? No real money' : 'Live mode'} ? Only matching-mode payments are included.</p><div className="ow-metric-grid ow-primary-grid"><MetricCard icon="wallet" label="Total revenue" value={money(summary.revenue.total)} note="Sum of the two sale categories" emphasis /><MetricCard icon="ticket" label="Single-Gym membership revenue" value={money(summary.revenue.single_gym_membership)} note="Each sale counted once" /><MetricCard icon="calendar" label="Individual booking revenue" value={money(summary.revenue.individual_booking)} note={`Paid, successfully checked-in bookings ? ${summary.revenue.mode}`} /></div>
        <Card title="Revenue Over Time"><p className="ow-caption">{data.grouping} purchase-date paid sales · INR · IST</p><ReportChart points={data.series} metric="revenue" title="Revenue Over Time" /></Card><RevenueBasis revenue={summary.revenue} />
        {selected === 'all' && <Card title="Revenue by gym">{data.revenue_by_gym.length ? <div className="ow-report-table" tabIndex={0}><table className="ow-table"><thead><tr><th>Gym</th><th>Single-Gym sales</th><th>Booking sales</th><th>Total</th></tr></thead><tbody>{data.revenue_by_gym.map(row => <tr key={row.gym_id}><td>{row.gym_name}</td><td>{money(row.single_gym_membership)}</td><td>{money(row.individual_booking)}</td><td>{money(row.total)}</td></tr>)}</tbody></table></div> : <EmptyState title="No sales in this period" />}</Card>}
      </section>
    </>}
    {!revenueOnly && <div key={`records:${scopeKey}`} className="ow-stack"><BookingRecords scope={scope} version={version} /><AttendanceRecords scope={scope} version={version} /></div>}
    <Transactions key={`transactions:${scopeKey}`} scope={scope} version={version} />
  </div>
}