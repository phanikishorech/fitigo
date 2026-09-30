import { useState } from 'react'
import type { User } from '../services/accountService'
import { dateLabel, localDate, money } from '../services/client'
import { dashboardService, notificationService } from './services'
import { useAdminResource, useListQuery } from './hooks'
import { Alert, DataCard, DatePicker, Details, EmptyState, Identity, Link, PageHeader, Pagination, Resource, StatusBadge, personName, readable } from './UI'

export default function Account({ page, user, roles }: { page: string; user: User; roles: string[] }) {
  if (page === 'reports') return <Reports />
  if (page === 'notifications') return <Notifications />
  if (page === 'profile') return <><PageHeader title="Admin profile" subtitle="Your verified administrator identity" /><DataCard><Identity name={personName(user)} caption={roles.map(readable).join(' · ')} /><Details rows={[["Name", personName(user)], ['Email', user.email], ['Phone', user.phone], ['User ID', `#${user.id}`], ['Roles', roles.map(readable).join(', ')]]} /><Alert>Profile editing and security settings are not available in the current admin API.</Alert></DataCard></>
  if (page === 'settings' || page === 'audit-logs') return <><PageHeader title={page === 'settings' ? 'Settings' : 'Audit Logs'} /><DataCard><EmptyState title="Not available yet" description="This capability is not exposed by the current backend. No placeholder records or controls are shown." action={<Link className="fg-button fg-button--primary" to="/admin/dashboard">Back to Dashboard</Link>} /></DataCard></>
  return <EmptyState title="404 · Page not found" description="This page may have moved, or the address may be incorrect." action={<Link className="fg-button fg-button--primary" to="/admin/dashboard">Back to Dashboard</Link>} />
}
function Reports() {
  const today = localDate(); const start = new Date(); start.setDate(start.getDate() - 29)
  const [from, setFrom] = useState(localDate(start)); const [to, setTo] = useState(today)
  const valid = !!from && !!to && from <= to
  const resource = useAdminResource(() => valid ? dashboardService.daily({ date_from: from, date_to: to, limit: 366 }) : Promise.resolve([]), `report:${from}:${to}`)
  return <><PageHeader title="Reports" subtitle="Daily booking activity reported by the backend" /><DataCard title="Daily booking report"><div className="ad-report-filters"><DatePicker label="From" value={from} max={to} onChange={setFrom} /><DatePicker label="To" value={to} min={from} onChange={setTo} /></div>{!valid ? <Alert tone="warning">Select a valid date range.</Alert> : <Resource resource={resource}>{rows => rows.length ? <><p className="ad-card-subtitle">Up to 366 reported dates, newest first. Paid totals follow the backend’s booking-date grouping; no transaction-date revenue is inferred.</p><div className="ad-report-table"><table className="ad-table"><caption className="srOnly">Daily booking report</caption><thead><tr>{['Date', 'Bookings', 'Confirmed', 'Cancelled', 'Expired', 'Paid total (INR)'].map(label => <th key={label} scope="col">{label}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.day}><th scope="row">{dateLabel(row.day)}</th><td>{row.total_bookings}</td><td>{row.confirmed_bookings}</td><td>{row.cancelled_bookings}</td><td>{row.expired_bookings}</td><td>{money(row.paid_amount_total)}</td></tr>)}</tbody></table></div><div className="ad-mobile-records">{rows.map(row => <article className="ad-mobile-card" key={row.day}><h3>{dateLabel(row.day)}</h3><Details rows={[["Bookings", row.total_bookings], ['Confirmed', row.confirmed_bookings], ['Cancelled', row.cancelled_bookings], ['Expired', row.expired_bookings], ['Paid total (INR)', money(row.paid_amount_total)]]} /></article>)}</div></> : <EmptyState title="No booking activity in this period." />}</Resource>}</DataCard></>
}
function Notifications() {
  const list = useListQuery(); const resource = useAdminResource(() => notificationService.list(list.offset), `notifications:${list.page}`)
  return <><PageHeader title="Notifications" subtitle="Events associated with your administrator account" /><DataCard><Resource resource={resource}>{rows => <>{rows.length ? <div className="ad-notification-list">{rows.slice(0, 20).map(row => <article key={row.id}><Identity icon="bell" name={readable(row.event_type)} caption={dateLabel(row.created_at)} /><StatusBadge status={row.status} /></article>)}</div> : <EmptyState title="No notifications yet." description="Events for your account will appear here." />}<Pagination page={list.page} count={Math.min(rows.length, 20)} hasMore={rows.length > 20} onPage={page => list.update({ page: String(page) })} /></>}</Resource></DataCard></>
}