import type { GymFinancialSettings } from './gymFinancialSettingsService'
import { Alert, Select } from './UI'

type Settlement = GymFinancialSettings['settlements']
const choices: { key: keyof Settlement; label: string; values: string[] }[] = [
  { key: 'single_gym_cycle', label: 'Single-Gym settlement cycle', values: ['UPFRONT', 'WEEKLY', 'MONTHLY'] },
  { key: 'timezone', label: 'Settlement timezone', values: ['Asia/Kolkata', 'UTC'] },
  { key: 'short_month', label: 'Short-month cutoff treatment', values: ['LAST_CALENDAR_DAY', 'NEXT_MONTH'] },
  { key: 'payout_eligibility', label: 'Payout eligibility', values: ['VERIFIED_NET_SOURCE_UNDISPUTED'] },
  { key: 'partial_settlement', label: 'Partial settlement', values: ['ALLOW_WITH_ALLOCATION_LINKS', 'FULL_ENTITLEMENT_ONLY'] },
  { key: 'failed_settlement', label: 'Failed settlement treatment', values: ['REMAIN_OUTSTANDING_REQUIRE_EVIDENCE'] }
]
export default function SettlementSettingsEditor({ value, onChange }: { value: Settlement; onChange: (value: Settlement) => void }) {
  const update = (key: keyof Settlement, next: unknown) => onChange({ ...value, [key]: next })
  return <fieldset><legend>Settlement readiness policy</legend><Alert>No unapproved defaults. These fields are saved with the same future-dated gym version, actor and reason. Missing required fields block payouts. Upfront entitlement does not imply immediate payment.</Alert>
    <div className="ag-grid">{choices.map(item => <Select key={item.key} label={item.label} value={String(value[item.key] ?? '')} onChange={next => update(item.key, next || null)} options={[{ value: '', label: 'Not configured' }, ...item.values.map(next => ({ value: next, label: next.replaceAll('_', ' ') }))]} />)}
      <label className="ad-field"><span>Settlement cutoff time</span><input type="time" step="1" value={value.cutoff_time ?? ''} onChange={event => update('cutoff_time', event.target.value ? event.target.value.length === 5 ? event.target.value + ':00' : event.target.value : null)} /></label>
      {([{ key: 'weekly_cutoff_day', label: 'Weekly cutoff day (Monday 0–Sunday 6)', min: 0, max: 6 }, { key: 'monthly_cutoff_day', label: 'Monthly cutoff day', min: 1, max: 31 }, { key: 'holding_days', label: 'Holding period in days', min: 0, max: 3660 }] as const).map(item => <label className="ad-field" key={item.key}><span>{item.label}</span><input type="number" min={item.min} max={item.max} step="1" value={value[item.key] ?? ''} onChange={event => update(item.key, event.target.value === '' ? null : Number(event.target.value))} /></label>)}
      <Select label="Permitted deductions" value={value.eligible_deductions == null ? '' : value.eligible_deductions.length === 0 ? 'NONE' : [...value.eligible_deductions].sort().join(',')} onChange={next => update('eligible_deductions', next === '' ? null : next === 'NONE' ? [] : next.split(','))} options={[{ value: '', label: 'Not configured' }, { value: 'NONE', label: 'Explicitly no deductions' }, { value: 'ACTUAL_TAX_WITHHOLDING', label: 'Evidenced tax withholding only' }, { value: 'APPROVED_SOURCE_ADJUSTMENT', label: 'Approved source adjustment only' }, { value: 'ACTUAL_TAX_WITHHOLDING,APPROVED_SOURCE_ADJUSTMENT', label: 'Both evidenced deduction types' }]} />
    </div><p>Gateway fee contributions are already deducted in net entitlement and cannot be deducted again here. Empty deductions mean none; unconfigured means blocked. No tax withholding rate is inferred.</p>
  </fieldset>
}