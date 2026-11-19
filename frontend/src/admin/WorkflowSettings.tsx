import { useState } from 'react'
import { request } from '../services/client'
import { useAdminResource } from './hooks'
import { Alert, DataCard, Details, EmptyState, Link, PageHeader, Pagination, Resource } from './UI'
import { istDateTime } from '../utils/membership'

type Settings = { payment: { enabled: boolean; provider: string | null; mode: string; wallet_test_credit: boolean }; limitations: Record<string, string> }
type Audit = { id: string; actor_id: number | null; action: string; resource_type: string; resource_id: number; timestamp: string; context: Record<string, string | number | boolean> }
export default function WorkflowSettings({ audit = false }: { audit?: boolean }) { return audit ? <AuditLog /> : <SettingsView /> }
function SettingsView() {
  const resource = useAdminResource(() => request<Settings>('/admin/settings', { cache: 'no-store' }), 'admin-settings')
  return <><PageHeader title="Runtime settings" subtitle="Deployment capabilities are read-only. Gym financial configuration has its own page." /><DataCard><Link to="/admin/financial-settings">Open Financial Settings</Link></DataCard><Resource resource={resource}>{data => <>
    <DataCard title="Payment configuration"><Details rows={[["Gateway", data.payment.enabled ? data.payment.provider : 'Unavailable'], ['Mode', data.payment.mode], ['Development wallet credits', data.payment.wallet_test_credit ? 'Enabled' : 'Disabled']]} /></DataCard>
    <DataCard title="Workflow limitations">{Object.entries(data.limitations).map(([key, value]) => <p key={key}>{value}</p>)}</DataCard>
  </>}</Resource></>
}
function AuditLog() {
  const [page, setPage] = useState(0)
  const resource = useAdminResource(() => request<{ items: Audit[]; total: number; coverage: string[]; operational_audit_enabled?: boolean }>(`/admin/audit-logs?limit=20&offset=${page * 20}`, { cache: 'no-store' }), `audit:${page}`)
  return <><PageHeader title="Recorded audit events" subtitle="Recorded operations with explicit coverage." /><Alert>This is not a complete platform audit log. Raw reasons and credentials are never shown. Expanded records begin only after operational audit is enabled.</Alert><Resource resource={resource}>{data => <>
    <p>Coverage: {(data.coverage || []).join(", ")}. Expanded audit {data.operational_audit_enabled ? "enabled" : "disabled"}.</p>
    {data.items.length ? data.items.map(item => <DataCard key={item.id} title={item.action.replaceAll('_', ' ')}><Details rows={[["Actor", item.actor_id ? `User #${item.actor_id}` : "System / legacy actor not recorded"], ['Resource', `${item.resource_type} #${item.resource_id}`], ['Recorded', istDateTime(item.timestamp)], ['Safe context', Object.values(item.context).join(' → ') || 'Not recorded']]} /></DataCard>) : <EmptyState title="No recorded events" />}
    <Pagination page={page} count={data.items.length} hasMore={(page + 1) * 20 < data.total} onPage={setPage} />
  </>}</Resource></>
}