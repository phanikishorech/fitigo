import { useRef, useState } from 'react'
import { useAdminResource } from './hooks'
import { useMutation } from '../hooks/useResource'
import { shareValid, type Share } from './agreementService'
import { gymFinancialSettingsService as service, type GymSettingsConfig, type SettingsInput, type SettingsVersion, type GymFinancialSettings } from './gymFinancialSettingsService'
import { istValue } from './membershipPlanService'
import { istDateTime } from '../utils/membership'
import { Alert, Button, DataCard, Details, EmptyState, Modal, PageHeader, Pagination, Resource, SearchInput, Select } from './UI'
import './agreements.css'

const categories = [{ key: 'individual', label: 'Individual bookings' }, { key: 'single_gym', label: 'Single-Gym memberships' }, { key: 'no_show', label: 'Authorized no-show' }] as const

function ShareFields({ label, value, onChange }: { label: string; value: Share; onChange: (value: Share) => void }) {
  return <fieldset><legend>{label}</legend><div className="ag-grid">{(['gym_percent', 'fitigo_percent'] as const).map(key => <label className="ad-field" key={key}><span>{key === 'gym_percent' ? 'Gym owner %' : 'FitiGo %'}</span><input type="number" min="0" max="100" step="0.01" required value={value[key]} onChange={event => onChange({ ...value, [key]: event.target.value })} /></label>)}</div>{!shareValid(value) && <Alert tone="warning">Percentages must total exactly 100.</Alert>}</fieldset>
}

function CommercialDetails({ value }: { value?: GymFinancialSettings }) {
  if (!value) return <p>Earlier agreement preserved. Contact your platform administrator for its original terms.</p>
  return <><Details rows={categories.flatMap(({ key, label }) => [[label, `Gym ${value[key].revenue.gym_percent}% / FitiGo ${value[key].revenue.fitigo_percent}%`], [`${label} gateway fees`, `Gym ${value[key].gateway_fee.gym_percent}% / FitiGo ${value[key].gateway_fee.fitigo_percent}%`]])} /><Details rows={[
    ['Multi-Gym reference', `INR ${value.multi_gym.reference_amount} per ${value.multi_gym.reference_visits} verified visits`],
    ['Multi-Gym gateway fees', `Gym ${value.multi_gym.gateway_fee.gym_percent}% / FitiGo ${value.multi_gym.gateway_fee.fitigo_percent}%`]
  ]} /></>
}

function Version({ row }: { row: SettingsVersion }) {
  return <details className="ag-version"><summary>Version {row.version} · {row.state.replaceAll('_', ' ')} · {istDateTime(row.effective_from)}</summary><Details rows={[
    ['Changed by', `User #${row.actor_id}`], ['Reason', row.reason], ['Recorded', istDateTime(row.created_at)],
    ['Effective until (exclusive)', row.applies_until ? istDateTime(row.applies_until) : 'Until superseded'],
    ['Agreement', row.terms?.financial_settings ? 'Gym-specific settings' : 'Legacy contract — preserved unchanged']
  ]} /><CommercialDetails value={row.terms?.financial_settings as GymFinancialSettings | undefined} /></details>
}

function Editor({ config, onSaved }: { config: GymSettingsConfig; onSaved: () => void }) {
  const [settings, setSettings] = useState(() => structuredClone(config.template!))
  const [starts, setStarts] = useState(''), [reason, setReason] = useState('')
  const [acknowledge, setAcknowledge] = useState(false), [replaceLegacy, setReplaceLegacy] = useState(false)
  const [review, setReview] = useState<SettingsInput | null>(null), [attempted, setAttempted] = useState(false)
  const key = useRef(''); const mutation = useMutation()
  const valid = categories.every(({ key }) => shareValid(settings[key].revenue) && shareValid(settings[key].gateway_fee)) && shareValid(settings.multi_gym.gateway_fee)
  return <form className="ag-form" onSubmit={event => {
    event.preventDefault()
    if (!valid || !acknowledge || (config.legacy_replacement_required && !replaceLegacy)) return
    const instant = istValue(starts)
    if (!starts || !Number.isFinite(Date.parse(instant))) { mutation.setError('Enter a valid effective date and time.'); return }
    key.current = crypto.randomUUID(); setAttempted(false)
    setReview({ mode: config.mode, gym_id: config.gym_id, expected_version: config.latest_version, expected_effective_version_id: config.effective?.id ?? null,
      effective_from: instant, settings: structuredClone(settings), reason: reason.trim(), acknowledge_configuration_only: acknowledge, acknowledge_legacy_replacement: replaceLegacy })
  }}>
    {categories.map(({ key, label }) => <fieldset key={key}><legend>{label}</legend><ShareFields label="Revenue sharing" value={settings[key].revenue} onChange={revenue => setSettings({ ...settings, [key]: { ...settings[key], revenue } })} /><ShareFields label="Actual gateway fee responsibility" value={settings[key].gateway_fee} onChange={gateway_fee => setSettings({ ...settings, [key]: { ...settings[key], gateway_fee } })} /></fieldset>)}
    <Alert>Single-Gym entitlement is upfront after verified purchase. A no-show requires explicit authorization; an unscanned QR is not authorization. Wallet-only funding has no gateway fee. Unknown provider fees leave net amounts pending.</Alert>
    <fieldset><legend>Multi-Gym monthly verified visits</legend><div className="ag-grid"><label className="ad-field"><span>Reference amount (INR)</span><input required type="number" min="0" max="9999999999" step="0.01" value={settings.multi_gym.reference_amount} onChange={event => setSettings({ ...settings, multi_gym: { ...settings.multi_gym, reference_amount: event.target.value } })} /></label><label className="ad-field"><span>Reference verified visits (divisor, not a cap)</span><input required type="number" min="1" max="1000000000" step="1" value={settings.multi_gym.reference_visits} onChange={event => setSettings({ ...settings, multi_gym: { ...settings.multi_gym, reference_visits: Number(event.target.value) } })} /></label></div><p>Monthly owner gross = reference amount ÷ reference visits × actual verified monthly visits. No visit or payout cap is introduced.</p><ShareFields label="Multi-Gym actual gateway fee responsibility" value={settings.multi_gym.gateway_fee} onChange={gateway_fee => setSettings({ ...settings, multi_gym: { ...settings.multi_gym, gateway_fee } })} /><Alert tone="warning">Monthly payouts use verified visits in India time. Each visit keeps its agreed settings. Gateway fees are shared once after membership completion. Monthly amounts become available after verified visits and fees are confirmed. Unallocated collections are separate; FitiGo earnings remain unapproved.</Alert></fieldset>
    <div className="ag-grid"><label className="ad-field"><span>Effective from (India time)</span><input type="datetime-local" required value={starts} onChange={event => setStarts(event.target.value)} /></label><label className="ad-field"><span>Change reason</span><textarea required minLength={3} maxLength={500} value={reason} onChange={event => setReason(event.target.value)} /></label></div>
    {config.legacy_replacement_required && <label className="ag-check"><input type="checkbox" checked={replaceLegacy} onChange={event => setReplaceLegacy(event.target.checked)} /><span>I reviewed the legacy contract and explicitly authorize its future replacement. Historical versions and transaction pins will not change.</span></label>}
    <label className="ag-check"><input type="checkbox" checked={acknowledge} onChange={event => setAcknowledge(event.target.checked)} /><span>I understand these settings apply from the selected date. Past purchases and payments stay unchanged.</span></label>
    {mutation.error && !review && <Alert tone="danger">{mutation.error}</Alert>}
    <Button type="submit" disabled={!valid || !acknowledge || (config.legacy_replacement_required && !replaceLegacy)}>Review future settings</Button>
    {review && <Modal title="Confirm gym financial settings" onClose={() => { if (!mutation.pending && !attempted) setReview(null) }}><p>{config.gym_name} · {config.mode} · Version {config.latest_version + 1} · {istDateTime(review.effective_from)}</p><p>{review.reason}</p><CommercialDetails value={review.settings} /><Alert>Past purchases stay unchanged. Saving settings does not send any payment.</Alert>{mutation.error && <Alert tone="danger">{mutation.error}</Alert>}{attempted && <p>Retry uses the same unchanged request. If the result is uncertain, reload the page to check history before editing.</p>}<Button loading={mutation.pending} onClick={() => { setAttempted(true); void mutation.run(async () => { await service.create(review, key.current); onSaved() }) }}>Save future version</Button>{!attempted && <Button variant="secondary" disabled={mutation.pending} onClick={() => setReview(null)}>Back to editing</Button>}</Modal>}
  </form>
}

function GymSettings({ mode, gymId }: { mode: 'test' | 'live'; gymId: number }) {
  const [page, setPage] = useState(0), [revision, setRevision] = useState(0), [saved, setSaved] = useState(false)
  const resource = useAdminResource(() => service.get(mode, gymId, page), `financial-settings:${mode}:${gymId}:${page}:${revision}`)
  return <Resource resource={resource}>{config => <DataCard title={config.gym_name}>{saved && <Alert tone="success">Future version saved. Historical transactions remain unchanged.</Alert>}{!config.available ? <Alert tone="warning">Commission settings are temporarily unavailable. Contact your platform administrator.</Alert> : <>
    <h3>Currently effective</h3>{config.effective ? <Version row={config.effective} /> : <Alert tone="warning">No effective configuration. The defaults below are a proposal only. Initialize this gym with an explicit future effective date.</Alert>}
    {config.template && <details className="ag-proposal"><summary>Configure a future version</summary><Editor key={`${config.latest_version}:${revision}`} config={config} onSaved={() => { setSaved(true); setPage(0); setRevision(value => value + 1) }} /></details>}
    <h3>Settings history</h3>{config.history.length ? config.history.map(row => <Version row={row} key={row.id} />) : <EmptyState title="No gym-specific versions" />}<Pagination page={page + 1} count={config.history.length} hasMore={(page + 1) * 20 < config.total} onPage={value => setPage(value - 1)} />
  </>}<Button variant="secondary" onClick={() => setRevision(value => value + 1)}>Reload settings and history</Button></DataCard>}</Resource>
}

export default function FinancialSettings() {
  const [mode, setMode] = useState<'test' | 'live'>('test'), [gymId, setGymId] = useState<number | null>(null)
  const [query, setQuery] = useState(''), [page, setPage] = useState(0)
  const gyms = useAdminResource(() => service.gyms(query, page), `financial-settings-gyms:${query}:${page}`)
  return <><PageHeader title="Commission Settings" subtitle="Set each gym's revenue sharing and gateway fee responsibility independently." /><DataCard><Select label="Payment environment" value={mode} onChange={value => setMode(value as 'test' | 'live')} options={[{ value: 'test', label: 'Sandbox / test' }, { value: 'live', label: 'Production / live' }]} /><SearchInput value={query} onChange={value => { setQuery(value); setPage(0) }} placeholder="Search gyms for commission settings" /><Resource resource={gyms}>{data => <><Select label="Select gym" value={gymId === null ? '' : String(gymId)} onChange={value => setGymId(value ? Number(value) : null)} options={[{ value: '', label: 'Choose a gym' }, ...(gymId && !data.items.some(gym => gym.id === gymId) ? [{ value: String(gymId), label: `Selected gym #${gymId}` }] : []), ...data.items.map(gym => ({ value: String(gym.id), label: `${gym.name} (#${gym.id})` }))]} /><p>{data.total} matching gyms. Search by name or use the page controls to view every gym.</p><Pagination page={page + 1} count={data.items.length} hasMore={(page + 1) * 20 < data.total} onPage={value => setPage(value - 1)} /></>}</Resource></DataCard>{gymId ? <GymSettings key={`${mode}:${gymId}`} mode={mode} gymId={gymId} /> : <EmptyState title="Select a gym to view its settings" />}</>
}
