import { request } from '../services/client'
import { useAdminResource } from './hooks'
import { Alert, Button, DataCard, PageHeader, Resource } from './UI'

type Report = { checks: { code: string; status: string; message: string }[]; queue_counts: Record<string, Record<string, number>>; production_certified: boolean; message: string }
export default function Readiness() {
  const resource = useAdminResource(() => request<Report>('/admin/readiness', { cache: 'no-store' }), 'admin-readiness')
  return <><PageHeader title="Readiness checks" subtitle="Read-only configuration and queue observations" action={<Button variant="secondary" onClick={resource.retry}>Refresh readiness</Button>} />
    <Alert>This report does not certify production readiness, send messages, run workers or execute migrations. Manual acceptance checks remain required.</Alert>
    <Resource resource={resource}>{data => <><p>{data.message}</p>{data.checks.map(check => <DataCard key={check.code} title={check.code.replaceAll('_', ' ')}><strong>{check.status.replaceAll('_', ' ')}</strong><p>{check.message}</p></DataCard>)}
      <DataCard title="Recorded queue counts">{Object.entries(data.queue_counts).map(([queue, values]) => <section key={queue}><h3>{queue.replaceAll('_', ' ')}</h3>{Object.entries(values).length ? Object.entries(values).map(([status, count]) => <p key={status}>{status}: {count}</p>) : <p>No recorded jobs.</p>}</section>)}</DataCard>
    </>}</Resource></>
}