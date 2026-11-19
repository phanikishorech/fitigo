import { useState } from 'react'
import { useAdminResource } from './hooks'
import { marketplaceService } from './marketplaceService'
import { Alert, DataCard, Pagination, Resource } from './UI'

export default function HistoricalFinancialReview({ mode }: { mode: 'test' | 'live' }) {
  const [page, setPage] = useState(0)
  const resource = useAdminResource(() => marketplaceService.historical(mode, page), `historical-finance:${mode}:${page}`)
  return <DataCard title="Historical financial review — no automatic adjustments"><Resource resource={resource}>{data => <><Alert>{data.notice}</Alert><p>{data.inconsistent_source_events} inconsistent source events. Global unclassified sources: {data.unclassified_environment_bookings} bookings, {data.unclassified_environment_memberships} memberships. This review uses the environment filter only.</p><div className="af-table"><table className="ad-table"><thead><tr><th>Source</th><th>Purchase reference</th><th>Review reasons</th></tr></thead><tbody>{data.items.map(row => <tr key={`${row.source_type}:${row.source_id}`}><td>{row.source_type} #{row.source_id}</td><td>{row.checkout_id}</td><td>{row.issues.map(issue => <div key={issue}>{issue.replaceAll('_', ' ')}</div>)}</td></tr>)}</tbody></table></div><Pagination page={page} count={data.items.length} hasMore={data.has_more} onPage={setPage} /></>}</Resource></DataCard>
}