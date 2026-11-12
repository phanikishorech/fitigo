import { useState, type ReactNode } from 'react'
import DateRangePicker, { dateRangeLabel } from '../components/common/DateRangePicker'
import { localDate, money } from '../services/client'
import { presetRange } from '../utils/dateRange'
import { analyticsCsv, comparison } from '../utils/analytics'
import { analyticsService, type Analytics as Report, type AnalyticsFilters, type AnalyticsMetrics, type Grain } from './analyticsService'
import { useAdminResource } from './hooks'
import { Button, DataCard, EmptyState, Icon, Link, MetricCard, PageHeader, Resource, Select, StatusBadge, Tabs } from './UI'
import './analytics.css'

const columns: { key: keyof AnalyticsMetrics; label: string; money?: boolean }[] = [
  { key: 'bookings', label: 'Bookings' }, { key: 'places', label: 'Places' },
  { key: 'confirmed', label: 'Confirmed' }, { key: 'pending', label: 'Pending' },
  { key: 'cancelled', label: 'Cancelled' }, { key: 'expired', label: 'Expired' },
  { key: 'attended', label: 'Attended' }, { key: 'no_show', label: 'No-show' },
  { key: 'paid_bookings', label: 'Verified paid' }, { key: 'paid_amount', label: 'Verified paid (INR)', money: true },
  { key: 'failed_payments', label: 'Payment failed' }, { key: 'refunded_payments', label: 'Refund recorded' },
  { key: 'review_required', label: 'Payment review' }
]
type MetricRow = AnalyticsMetrics & { key: string; label: ReactNode; exportLabel: string; context: string }

function MetricsTable({ rows, title, report }: { rows: MetricRow[]; title: string; report: Report }) {
  const [search, setSearch] = useState(''), [page, setPage] = useState(1), [sort, setSort] = useState('bookings')
  const filtered = rows.filter(row => `${row.exportLabel} ${row.context}`.toLowerCase().includes(search.trim().toLowerCase()))
    .sort((a, b) => sort === 'name' ? a.exportLabel.localeCompare(b.exportLabel) : Number(b[sort as keyof AnalyticsMetrics]) - Number(a[sort as keyof AnalyticsMetrics]) || a.exportLabel.localeCompare(b.exportLabel))
  const pages = Math.max(1, Math.ceil(filtered.length / 20)), visiblePage = Math.min(page, pages)
  const visible = filtered.slice((visiblePage - 1) * 20, visiblePage * 20)
  function exportCsv() {
    const headers = ['Date from', 'Date to', 'Date basis', 'Paid amount mode', 'Name / period', 'Location / context', ...columns.map(col => col.label)]
    const csv = analyticsCsv(headers, filtered.map(row => [report.date_from, report.date_to, report.scope.date_basis, report.scope.mode,
      row.exportLabel, row.context, ...columns.map(col => row[col.key])]))
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }))
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `fitigo-${title.toLowerCase().replaceAll(' ', '-')}-${report.date_from}-${report.date_to}.csv`; anchor.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <DataCard title={title} action={<Button variant="secondary" disabled={!filtered.length} onClick={exportCsv}><Icon name="share" size={16} />Export CSV</Button>}>
    <div className="aa-table-tools"><label className="ad-field"><span>Search {title.toLowerCase()}</span><input type="search" value={search} maxLength={100} onChange={e => { setSearch(e.target.value); setPage(1) }} placeholder="Name or location…" /></label>
      <Select label="Sort by" value={sort} onChange={value => { setSort(value); setPage(1) }} options={[{ value: 'bookings', label: 'Most bookings' }, { value: 'paid_amount', label: 'Highest verified paid amount' }, { value: 'cancelled', label: 'Most cancellations' }, { value: 'name', label: 'Name / period' }]} />
      <span>{filtered.length} rows · CSV includes all matching rows</span></div>
    {!filtered.length ? <EmptyState title="No matching rows" description="Adjust the search or location filters." /> : <>
      <div className="aa-table-scroll" role="region" aria-label={`${title} — scroll for all metrics`} tabIndex={0}><table className="ad-table"><caption className="srOnly">{title} · {dateRangeLabel(report)}</caption><thead><tr><th scope="col">{title === 'Time periods' ? 'Period' : 'Name / location'}</th>{columns.map(col => <th scope="col" key={col.key}>{col.label}</th>)}</tr></thead>
        <tbody>{visible.map(row => <tr key={row.key}><th scope="row"><div>{row.label}</div><small>{row.context}</small></th>{columns.map(col => <td key={col.key}>{col.money ? money(row[col.key] as string) : row[col.key]}</td>)}</tr>)}</tbody></table></div>
      <nav className="aa-pagination" aria-label={`${title} pagination`}><span>Page {visiblePage} of {pages}</span><Button variant="secondary" disabled={visiblePage === 1} onClick={() => setPage(visiblePage - 1)}>Previous</Button><Button variant="secondary" disabled={visiblePage === pages} onClick={() => setPage(visiblePage + 1)}>Next</Button></nav>
    </>}
  </DataCard>
}

function Breakdown({ title, entries, denominator }: { title: string; entries: [string, number][]; denominator: number }) {
  return <DataCard title={title}><div className="aa-breakdown">{entries.map(([name, count]) => <div key={name}><div><span>{name}</span><strong>{count.toLocaleString()}</strong></div><div className="aa-track" aria-hidden="true"><span style={{ width: `${denominator ? Math.min(100, count / denominator * 100) : 0}%` }} /></div></div>)}</div></DataCard>
}

export default function Analytics() {
  const [filters, setFilters] = useState<AnalyticsFilters>(() => ({ ...presetRange('last30', localDate()), grain: 'day' }))
  const [view, setView] = useState('gyms')
  const resource = useAdminResource(signal => analyticsService.report(filters, signal), JSON.stringify(filters))
  return <div className="aa-page"><PageHeader title="Analytics" subtitle="Understand booking activity across time, gyms and locations." action={<Button variant="secondary" onClick={resource.retry}><Icon name="chart" size={17} />Refresh analytics</Button>} />
    <DateRangePicker value={filters} onChange={range => setFilters(previous => ({ ...previous, ...range }))} />
    <Resource resource={resource}>{report => {
      const locationOptions = (key: 'country' | 'state' | 'city') => [{ value: '*', label: `All ${key === 'country' ? 'countries' : key === 'city' ? 'cities' : 'states'}` },
        ...[...new Set(report.options.filter(g => (key === 'country' || filters.country === undefined || g.country === filters.country) &&
          (key !== 'city' || filters.state === undefined || g.state === filters.state)).map(g => g[key]))].sort().map(value => ({ value: JSON.stringify(value), label: value || 'Not specified' }))]
      const selectedGyms = report.options.filter(g => (filters.country === undefined || g.country === filters.country) && (filters.state === undefined || g.state === filters.state) && (filters.city === undefined || g.city === filters.city))
      const summary = report.summary, previous = report.previous
      const max = Math.max(1, ...report.series.map(row => row.bookings))
      const rows: MetricRow[] = view === 'gyms' ? report.gyms.map(g => ({ ...g, key: String(g.id), exportLabel: g.name,
        label: <Link className="ad-text-link" to={`/admin/gyms/${g.id}`}>{g.name}</Link>, context: `${[g.city, g.state, g.country].filter(Boolean).join(', ') || 'Location not specified'} · ${g.unique_customers} unique customers · ${g.status.toLowerCase()}` }))
        : view === 'locations' ? report.locations.map(g => ({ ...g, key: JSON.stringify([g.country, g.state, g.city]), exportLabel: g.city || 'City not specified', label: g.city || 'City not specified', context: `${g.state || 'State not specified'} · ${g.country || 'Country not specified'} · ${g.gyms} gyms (${g.active_gyms} active)` }))
        : report.series.map(row => ({ ...row, key: row.period, exportLabel: row.period, label: row.period, context: `${row.date_from} – ${row.date_to}` }))
      return <>
        <DataCard><div className="aa-filters"><Select label="Group time by" value={filters.grain} onChange={value => setFilters(f => ({ ...f, grain: value as Grain }))} options={[{ value: 'day', label: 'Daily' }, { value: 'week', label: 'Weekly (Monday)' }, { value: 'month', label: 'Monthly' }]} />
          {(['country', 'state', 'city'] as const).map(key => <Select key={key} label={key[0].toUpperCase() + key.slice(1)} value={filters[key] === undefined ? '*' : JSON.stringify(filters[key])} options={locationOptions(key)} onChange={value => setFilters(f => ({ ...f, [key]: value === '*' ? undefined : JSON.parse(value), gym_id: undefined, ...(key === 'country' ? { state: undefined, city: undefined } : key === 'state' ? { city: undefined } : {}) }))} />)}
          <Select label="Gym" value={String(filters.gym_id || '')} onChange={value => setFilters(f => ({ ...f, gym_id: value ? Number(value) : undefined }))} options={[{ value: '', label: 'All gyms' }, ...selectedGyms.map(g => ({ value: String(g.id), label: `${g.name} (#${g.id})` }))]} />
          <Button variant="text" onClick={() => setFilters(f => ({ date_from: f.date_from, date_to: f.date_to, grain: f.grain }))}>Reset filters</Button></div></DataCard>
        <div className="aa-scope"><StatusBadge status={report.scope.mode === 'test' ? 'TEST MODE' : 'LIVE MODE'} /><p>Booking counts include all payment modes. Money shows verified <strong>{report.scope.mode}</strong> gateway payments only, by scheduled visit date (IST), not settlements or earned revenue.</p></div>
        <div className="ad-metrics"><MetricCard title="Total bookings" value={summary.bookings.toLocaleString()} caption={comparison(summary.bookings, previous.bookings)} icon="ticket" />
          <MetricCard title="Reserved places" value={summary.places.toLocaleString()} caption="Visitor quantities across all booking statuses" icon="user" />
          <MetricCard title="Unique customers" value={summary.unique_customers.toLocaleString()} caption={comparison(summary.unique_customers, previous.unique_customers)} icon="user" />
          <MetricCard title="Verified paid amount" value={money(summary.paid_amount)} caption={`${summary.paid_bookings} paid bookings · ${comparison(Number(summary.paid_amount), Number(previous.paid_amount))}`} icon="wallet" /></div>
        <div className="aa-context"><span><strong>{report.catalog.gyms}</strong> gyms in scope</span><span><strong>{report.catalog.active_gyms}</strong> currently approved & active</span><span><strong>{report.catalog.gyms_with_bookings}</strong> gyms with bookings</span><span><strong>{summary.confirmation_rate === null ? '—' : `${summary.confirmation_rate}%`}</strong> confirmed / all bookings</span><span><strong>{summary.cancellation_rate === null ? '—' : `${summary.cancellation_rate}%`}</strong> cancelled / all bookings</span></div>
        <p className="ad-card-subtitle">Comparison: {previous.date_from} – {previous.date_to} (previous equal-length period). Gym/location attributes reflect the current catalog. Unique customer counts are not additive across gyms.</p>
        <DataCard title="Booking trend"><p className="ad-card-subtitle">{dateRangeLabel(report)} · {report.grain} buckets · partial weeks/months clipped to the selected range</p>
          {!summary.bookings ? <EmptyState title="No bookings in this period" description="Your gym catalog is still shown below. Activity appears when new bookings are created." /> : <div className="aa-chart-scroll" tabIndex={0} role="region" aria-label="Booking trend chart; exact values in Time periods table"><div className="aa-chart" style={{ minWidth: Math.max(400, report.series.length * 30) }} role="img" aria-label={`${summary.bookings} bookings across ${report.series.length} periods`}>{report.series.map(row => <div className="aa-chart-col" key={row.period}><div className="aa-chart-track"><span style={{ height: `${row.bookings / max * 100}%` }} title={`${row.date_from} – ${row.date_to}: ${row.bookings} bookings`} /></div><small>{row.period.slice(5)}</small></div>)}</div></div>}
          <Button variant="text" onClick={() => setView('periods')}>View exact period data</Button>
        </DataCard>
        <div className="aa-breakdown-grid"><Breakdown title="Booking status" denominator={summary.bookings} entries={[
          ['Confirmed', summary.confirmed], ['Pending payment', summary.pending], ['Cancelled', summary.cancelled], ['Expired', summary.expired], ['Other', Math.max(0, summary.bookings - summary.confirmed - summary.pending - summary.cancelled - summary.expired)]]} />
          <Breakdown title="Attendance on these bookings" denominator={summary.bookings} entries={[
            ['Attended', summary.attended], ['Marked no-show', summary.no_show], ['Not marked / other', Math.max(0, summary.bookings - summary.attended - summary.no_show)]]} />
          <Breakdown title="Payment signals" denominator={summary.bookings} entries={[
            ['Verified paid (selected mode)', summary.paid_bookings], ['Failed payment record', summary.failed_payments], ['Refund / partial refund record', summary.refunded_payments], ['Checkout needs review', summary.review_required]]} /></div>
        <p className="ad-card-subtitle">Attendance counts bookings, not check-in scans or individual visitors. Payment signals can overlap and are not a conversion funnel. No-show means explicitly marked, never inferred from missing attendance.</p>
        <Tabs label="Analytics table" value={view} onChange={setView} options={[{ value: 'gyms', label: 'Gym-wise' }, { value: 'locations', label: 'Location-wise' }, { value: 'periods', label: 'Time periods' }]} />
        <MetricsTable key={`${view}:${JSON.stringify(filters)}`} rows={rows} title={view === 'gyms' ? 'Gym performance' : view === 'locations' ? 'Location performance' : 'Time periods'} report={report} />
        <details className="aa-definitions"><summary>Metric definitions & payment exclusions</summary><p>{report.scope.basis}</p><p>Places include cancelled and expired reservations. Current gym status is not historical status. Membership entitlements, wallet top-ups, refunds initiated, and provider settlements are not included as booking revenue.</p><p>Last generated: {new Date(report.generated_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST. Custom date ranges support up to 366 days; all matching gym/location rows are included.</p></details>
      </>
    }}</Resource>
  </div>
}