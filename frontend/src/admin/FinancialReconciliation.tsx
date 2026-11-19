import { useRef, useState } from 'react'
import { useAdminResource } from './hooks'
import { useMutation } from '../hooks/useResource'
import { Alert, Button, DataCard, Details, EmptyState, Link, Modal, PageHeader, Pagination, Resource, Select, Tabs } from './UI'
import { reconciliationService as service, type ReconciliationView, type ReviewDetail } from './reconciliationService'
import { money } from '../services/client'
import './agreements.css'

const views: { value: ReconciliationView; label: string }[] = [
  { value: 'individual', label: 'Individual' }, { value: 'single_gym', label: 'Single-Gym' }, { value: 'no_show', label: 'Authorized no-show' },
  { value: 'multi_gym', label: 'Multi-Gym months' }, { value: 'fees', label: 'Gateway fees' }, { value: 'sources', label: 'Tax / source evidence' },
  { value: 'collections', label: 'Unallocated collections' }, { value: 'balances', label: 'Payout balances' }, { value: 'corrections', label: 'Corrections / differences' }
]
const jsonStyle = { whiteSpace: 'pre-wrap' as const, overflowWrap: 'anywhere' as const }

function RecordTrace({ mode, kind, id, onClose }: { mode: 'test' | 'live'; kind: string; id: string; onClose: () => void }) {
  const resource = useAdminResource(() => service.record(mode, kind, id), `trace:${mode}:${kind}:${id}`)
  return <Modal title="Immutable source snapshot" onClose={onClose}><Resource resource={resource}>{data => <><Alert tone={data.integrity_valid ? 'success' : 'danger'}>Snapshot integrity {data.integrity_valid ? 'verified' : 'FAILED — review required'}</Alert><p>{data.kind} · {data.id}</p><pre style={jsonStyle}>{JSON.stringify(data.snapshot, null, 2)}</pre><p>{data.snapshot_hash}</p></>}</Resource></Modal>
}

function TraceActions({ row, inspect }: { row: Record<string, unknown>; inspect: (kind: string, id: string) => void }) {
  const trace = row.trace as Record<string, unknown> | undefined
  const targets: { kind: string; id: string }[] = []
  for (const key of ['source_evidence_id', 'basis_evidence_id', 'fee_evidence_id']) if (typeof trace?.[key] === 'string') targets.push({ kind: 'source', id: trace[key] as string })
  for (const key of ['source_evidence_ids', 'fee_evidence_ids']) if (Array.isArray(trace?.[key])) for (const id of trace[key]) if (typeof id === 'string') targets.push({ kind: 'source', id })
  if (typeof trace?.monthly_calculation_id === 'string') targets.push({ kind: 'month', id: trace.monthly_calculation_id })
  if (typeof trace?.membership_fee_budget_id === 'string') targets.push({ kind: 'fee_budget', id: trace.membership_fee_budget_id })
  if (row.entry_kind && typeof row.id === 'string') targets.push({ kind: 'allocation', id: row.id })
  return <div className="ag-actions">{targets.filter((target, index) => targets.findIndex(other => other.kind === target.kind && other.id === target.id) === index).map(target => <Button key={`${target.kind}:${target.id}`} variant="secondary" onClick={() => inspect(target.kind, target.id)}>Inspect {target.kind} {target.id}</Button>)}</div>
}

function ReviewDecision({ detail, onSaved }: { detail: ReviewDetail; onSaved: () => void }) {
  const [status, setStatus] = useState('NEEDS_EVIDENCE'), [reason, setReason] = useState(''), [acknowledge, setAcknowledge] = useState(false), [protectedAck, setProtectedAck] = useState(false)
  const mutation = useMutation(), fixed = useRef<{ body: Record<string, unknown>; key: string } | null>(null)
  const [attempted, setAttempted] = useState(false)
  return <form className="ag-form" onSubmit={event => { event.preventDefault(); if (!acknowledge) return; if (!fixed.current) fixed.current = { key: crypto.randomUUID(), body: { mode: detail.case.mode, expected_revision: detail.case.revision, expected_impact_hash: detail.impact_hash, status, reason: reason.trim(), acknowledge_no_execution: acknowledge, acknowledge_reserved_paid: protectedAck } }; setAttempted(true); void mutation.run(async () => { await service.decide(detail.case.case_id, fixed.current!.body, fixed.current!.key); onSaved() }) }}>
    <fieldset disabled={attempted}><Select label="Review decision" value={status} onChange={setStatus} options={['NEEDS_EVIDENCE', 'APPROVED_FOR_RECONCILIATION', 'REJECTED'].map(value => ({ value, label: value.replaceAll('_', ' ') }))} /><label className="ad-field"><span>Decision reason</span><textarea minLength={3} maxLength={500} required value={reason} onChange={event => setReason(event.target.value)} /></label><label className="ag-check"><input type="checkbox" checked={protectedAck} onChange={event => setProtectedAck(event.target.checked)} /><span>I explicitly reviewed the listed reserved/paid amounts.</span></label><label className="ag-check"><input type="checkbox" required checked={acknowledge} onChange={event => setAcknowledge(event.target.checked)} /><span>This decision does not execute an adjustment, release a reservation, activate processing, or pay money.</span></label></fieldset>
    {mutation.error && <Alert tone="danger">{mutation.error}</Alert>}{attempted && <p>Retry sends the unchanged request. Reload the review before making a different decision.</p>}<Button type="submit" loading={mutation.pending} disabled={!acknowledge}>Record review decision</Button>
  </form>
}

function ReviewDetails({ mode, id, onClose, onSaved }: { mode: 'test' | 'live'; id: string; onClose: () => void; onSaved: () => void }) {
  const resource = useAdminResource(() => service.detail(mode, id), `review:${mode}:${id}`)
  return <Modal title="Financial correction review" onClose={onClose}><Resource resource={resource}>{data => <><Alert>Independent Admin approval is required. Approval is review-only; original records and financial safeguards remain unchanged.</Alert><h3>Current affected records</h3><pre style={jsonStyle}>{JSON.stringify(data.impact, null, 2)}</pre><h3>Append-only history</h3>{data.history.map(row => <details key={row.id}><summary>Revision {row.revision} · {row.status} · User #{row.actor_id}</summary><p>{row.reason}</p><pre style={jsonStyle}>{JSON.stringify(row.snapshot, null, 2)}</pre></details>)}{['OPEN', 'NEEDS_EVIDENCE'].includes(data.case.status) && <ReviewDecision detail={data} onSaved={() => { onSaved(); onClose() }} />}</>}</Resource></Modal>
}

function Reviews({ mode, gymId }: { mode: 'test' | 'live'; gymId: number | null }) {
  const [page, setPage] = useState(0), [revision, setRevision] = useState(0), [selected, setSelected] = useState<string | null>(null)
  const [source, setSource] = useState(''), [kind, setKind] = useState('LATE_VISIT'), [reason, setReason] = useState(''), [attempted, setAttempted] = useState(false)
  const fixed = useRef<{ body: Record<string, unknown>; key: string } | null>(null), mutation = useMutation()
  const resource = useAdminResource(() => service.reviews(mode, gymId, page), `reviews:${mode}:${gymId}:${page}:${revision}`)
  return <DataCard title="Controlled correction reviews"><Alert>Late visits, finalized months, closed fee budgets, and reserved/paid amounts require explicit review. No financial correction is executed here.</Alert>{gymId && <form className="ag-form" onSubmit={event => { event.preventDefault(); if (!fixed.current) fixed.current = { key: crypto.randomUUID(), body: { mode, gym_id: gymId, source_evidence_id: source.trim(), kind, reason: reason.trim() } }; setAttempted(true); void mutation.run(async () => { const row = await service.create(fixed.current!.body, fixed.current!.key); setSelected(row.case_id); setRevision(value => value + 1); fixed.current = null; setAttempted(false); setReason(''); setSource('') }) }}><fieldset disabled={attempted}><label className="ad-field"><span>Original source evidence UUID</span><input required minLength={36} maxLength={36} value={source} onChange={event => setSource(event.target.value)} /></label><Select label="Correction review type" value={kind} onChange={setKind} options={['LATE_VISIT', 'MONTH_CORRECTION', 'CLOSED_FEE_BUDGET', 'RESERVED_OR_PAID'].map(value => ({ value, label: value.replaceAll('_', ' ') }))} /><label className="ad-field"><span>Review reason</span><textarea required minLength={3} maxLength={500} value={reason} onChange={event => setReason(event.target.value)} /></label></fieldset>{mutation.error && <Alert tone="danger">{mutation.error}</Alert>}<Button type="submit" loading={mutation.pending}>Open review only</Button>{attempted && <p>Retry preserves this request. Reload the page to check history before changing it.</p>}</form>}
    {!gymId && <p>Select a gym to open a review.</p>}<Resource resource={resource}>{data => <>{data.items.map(row => <div key={row.id}><p>{row.kind} · {row.status} · Gym #{row.gym_id} · Revision {row.revision}</p><Button variant="secondary" onClick={() => setSelected(row.case_id)}>Inspect review {row.case_id}</Button></div>)}{!data.items.length && <EmptyState title="No correction reviews" />}<Pagination page={page} count={data.items.length} hasMore={(page + 1) * 20 < data.total} onPage={setPage} /></>}</Resource>{selected && <ReviewDetails mode={mode} id={selected} onClose={() => setSelected(null)} onSaved={() => setRevision(value => value + 1)} />}</DataCard>
}

export default function FinancialReconciliation() {
  const [trace, setTrace] = useState<{ kind: string; id: string } | null>(null)
  const [mode, setMode] = useState<'test' | 'live'>('test'), [view, setView] = useState<ReconciliationView>('sources'), [gym, setGym] = useState(''), [page, setPage] = useState(0)
  const gymId = /^\d+$/.test(gym) && Number.isSafeInteger(Number(gym)) && Number(gym) > 0 ? Number(gym) : null
  const resource = useAdminResource(() => service.report(mode, view, gymId, page), `reconciliation:${mode}:${view}:${gymId}:${page}`)
  return <><PageHeader title="Financial Reconciliation" subtitle="Readiness, source evidence and review controls. No activation or transfers." /><DataCard><div className="ag-grid"><Select label="Environment" value={mode} onChange={value => { setMode(value as 'test' | 'live'); setPage(0) }} options={[{ value: 'test', label: 'Sandbox / test' }, { value: 'live', label: 'Production / live' }]} /><label className="ad-field"><span>Gym ID (blank = all gyms)</span><input type="number" min="1" step="1" value={gym} onChange={event => { setGym(event.target.value); setPage(0) }} /></label></div><Link to="/admin/financial-settings">Manage future-dated Financial Settings</Link><Tabs label="Reconciliation views" value={view} options={views} onChange={value => { setView(value as ReconciliationView); setPage(0) }} /></DataCard>
    <Resource resource={resource}>{data => <><DataCard title="Activation controls"><Alert>{data.controls.notice}</Alert><Details rows={Object.entries(data.controls.gates).map(([key, value]) => [key, value ? 'Enabled in runtime' : 'Disabled'])} /><p>Schema ready: {data.controls.schema_ready ? 'Yes' : 'No'} · Activation authorized: No</p>{data.controls.missing_tables.length > 0 && <Alert tone="warning">Not deployed: {data.controls.missing_tables.join(', ')}</Alert>}<ul>{data.controls.checks.map(check => <li key={check}>{check}</li>)}</ul></DataCard>
      <DataCard title={views.find(item => item.value === view)?.label}><Alert>{data.notice}</Alert>{data.available ? <><h3>Current page totals only</h3><Details rows={Object.entries(data.page_totals).map(([key, value]) => [key.replaceAll('_', ' '), value === null ? 'Unknown / unresolved' : money(value)])} />{data.items.map((row, index) => <details className="ag-version" key={String(row.id ?? index)}><summary>{String(row.id)} · {String(row.status ?? row.category ?? 'Source evidence')}</summary><pre style={jsonStyle}>{JSON.stringify(row, null, 2)}</pre><TraceActions row={row} inspect={(kind, id) => setTrace({ kind, id })} /></details>)}{!data.items.length && <EmptyState title="No records in this scope" />}{data.monthly_history && <><h3>Monthly finalization and correction history</h3><p>Historical revisions are not additive.</p>{data.monthly_history.map(row => <details className="ag-version" key={String(row.id)}><summary>{String(row.period)} / Gym #{String(row.gym_id)} / Revision {String(row.revision)}</summary><pre style={jsonStyle}>{JSON.stringify(row, null, 2)}</pre><Button variant="secondary" onClick={() => setTrace({ kind: 'month', id: String(row.id) })}>Inspect monthly snapshot</Button></details>)}</>}<Pagination page={page} count={data.items.length} hasMore={(page + 1) * 20 < Math.max(data.total, data.monthly_history_total ?? 0)} onPage={setPage} /><p>Collection totals are checkout-wide, not gym-prorated. Multi-Gym collections are not FitiGo revenue. Reserved and approved balances overlap; do not add them together.</p></> : <EmptyState title="Financial schema is not deployed" description="No report values are manufactured from absent tables." />}</DataCard>{view === 'corrections' && data.available && <Reviews key={`${mode}:${gymId}`} mode={mode} gymId={gymId} />}</>}</Resource>
    {trace && <RecordTrace mode={mode} kind={trace.kind} id={trace.id} onClose={() => setTrace(null)} />}
  </>
}