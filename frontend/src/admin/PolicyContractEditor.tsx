import { useState } from 'react'
import { agreementService, type AgreementTerms, type AgreementConfig, type PolicySchema, type PolicyReadiness } from './agreementService'
import { Alert, Button, Details } from './UI'
import { useMutation } from '../hooks/useResource'

const label = (value: string) => value.replaceAll('_', ' ').toLowerCase().replace(/^./, c => c.toUpperCase())
export function PolicyStatus({ value }: { value?: PolicyReadiness }) {
  if (!value) return <p>Not configured: no policy validation result is available.</p>
  return <section aria-label="Policy readiness"><h4>{label(value.status)}</h4><p>{value.reason}</p><p>Posting eligibility: blocked. Phase 2 does not enable calculations, recognition or statutory reporting.</p><Details rows={Object.entries(value.sections).map(([key, section]) => [label(key), `${label(section.status)}${section.missing_fields.length ? ` — Missing: ${section.missing_fields.join(', ')}` : ''}`])} />{value.contexts && <Details rows={Object.entries(value.contexts).map(([key, context]) => [label(key), `${context.policy_ready ? 'Policy configured' : 'Blocked: '+context.blocked_policies.join(', ')} · Calculation not implemented`])} />}</section>
}

export function SchemaFields({ schema, root, value, onChange, path = '' }: { schema: PolicySchema; root: PolicySchema; value: unknown; onChange: (value: unknown) => void; path?: string }) {
  if (schema.$ref) schema = root.$defs?.[schema.$ref.split('/').at(-1)!] || schema
  const nullable = schema.anyOf?.some(s => s.type === 'null') || false
  if (schema.anyOf) {
    schema = { ...schema, ...schema.anyOf.filter(s => s.type !== 'null')[0], anyOf: undefined }
    if (schema.$ref) schema = root.$defs?.[schema.$ref.split('/').at(-1)!] || schema
  }
  if (schema.const !== undefined) {
    if (nullable) return <label className="ad-field"><span>{label(path.split('.').at(-1)!)}</span><select aria-label={path} value={value == null ? '' : String(value)} onChange={e => onChange(e.target.value || null)}><option value="">Not configured</option><option value={String(schema.const)}>{label(String(schema.const))}</option></select></label>
    return <p>{label(path.split('.').at(-1)!)}: <strong>{String(schema.const)}</strong></p>
  }
  if (schema.properties) {
    const record = (value || {}) as Record<string, unknown>
    return <div className="ag-form">{Object.entries(schema.properties).map(([key, child]) => {
      const content = <SchemaFields schema={child} root={root} value={record[key]} path={path ? `${path}.${key}` : key} onChange={v => onChange({ ...record, [key]: v })} />
      return child.$ref || child.type === 'object' ? <details key={key}><summary>{label(key)}</summary>{content}</details> : <div key={key}>{content}</div>
    })}</div>
  }
  if (schema.type === 'array') {
    const selected = value as string[] | null
    return <fieldset><legend>{label(path.split('.').at(-1)!)}</legend><label className="ag-check"><input type="checkbox" checked={selected != null} onChange={e => onChange(e.target.checked ? [] : null)} />Explicitly configured (no boxes selected means no deductions)</label>{selected != null && schema.items?.enum?.map(option => <label className="ag-check" key={option}><input type="checkbox" checked={selected.includes(option)} onChange={e => onChange(e.target.checked ? [...selected, option] : selected.filter(v => v !== option))} />{label(option)}</label>)}</fieldset>
  }
  if (schema.enum) return <label className="ad-field"><span>{label(path.split('.').at(-1)!)}</span><select aria-label={path} value={value == null ? '' : String(value)} onChange={e => onChange(e.target.value || null)}>{nullable && <option value="">Not configured</option>}{schema.enum.map(v => <option value={v} key={v}>{label(v)}</option>)}</select></label>
  const numeric = schema.type === 'integer' || schema.type === 'number'
  return <label className="ad-field"><span>{label(path.split('.').at(-1)!)}</span><input aria-label={path} type={numeric ? 'number' : 'text'} step={schema.type === 'integer' ? '1' : numeric ? '0.01' : undefined} min={schema.minimum} max={schema.maximum} maxLength={schema.maxLength} placeholder="Not configured" value={value == null ? '' : String(value)} onChange={e => onChange(e.target.value === '' && nullable ? null : schema.type === 'integer' ? Number(e.target.value) : e.target.value)} /><small>{path.endsWith('weekly_cutoff_day') ? '0 = Monday, 6 = Sunday.' : path.endsWith('cutoff_time') ? 'HH:mm:ss; select the timezone separately.' : ''}</small></label>
}

export default function PolicyContractEditor({ config, terms, onChange }: { config: AgreementConfig; terms: AgreementTerms; onChange: (value: AgreementTerms) => void }) {
  const [readiness, setReadiness] = useState<{ key: string; value: PolicyReadiness }>(), mutation = useMutation()
  const catalog = config.policy_catalog
  if (!catalog) return <Alert>Policy contract controls require the Phase 2 backend. Existing terms remain unchanged.</Alert>
  return <fieldset><legend>Phase 2 — policy and evidence contract</legend><Alert>Commercial choices start unset. An approval reference records administrator attestation, not CA verification. No setting enables posting. Custom “Other approved” methods remain unsupported.</Alert><label className="ag-check"><input type="checkbox" checked={!!terms.policy_contract} onChange={e => { setReadiness(undefined); onChange({ ...terms, policy_contract: e.target.checked ? structuredClone(catalog.empty) : null }) }} />Include policy contract version 2 in this new agreement version</label>{terms.policy_contract && <><p>Selection contexts are independent. No purchase/service instant is selected automatically. Existing percentages, rates, limits and settlement frequencies above remain the commercial source.</p><SchemaFields schema={catalog.schema} root={catalog.schema} value={terms.policy_contract} onChange={value => { setReadiness(undefined); onChange({ ...terms, policy_contract: value as Record<string, unknown> }) }} /><Button variant="secondary" loading={mutation.pending} onClick={() => void mutation.run(async () => setReadiness({ key: JSON.stringify(terms), value: await agreementService.validatePolicy(terms) }))}>Validate policy readiness</Button>{mutation.error && <Alert tone="danger">{mutation.error}</Alert>}<PolicyStatus value={readiness?.key === JSON.stringify(terms) ? readiness.value : undefined} /></>}</fieldset>
}