import { useId, useState, type ReactNode } from 'react'
import { navigate } from '../router'
import { money } from '../services/client'
import { planDuration, type PlatformPlan } from '../services/platformMembershipService'
import { useMutation } from '../hooks/useResource'
import { useAdminResource } from './hooks'
import { adminMembershipPlans, editablePlan, planAdminError, utcInput, utcValue, type AdminPlanDetail, type OfferInput, type PlanInput } from './membershipPlanService'
import { Alert, Button, DataCard, EmptyState, Icon, Link, Modal, PageHeader, Resource, StatusBadge, useToast } from './UI'

const basePath = '/admin/membership-plans'

export default function MembershipPlans({ id, create = false, offer = false }: { id?: number; create?: boolean; offer?: boolean }) {
  if (create) return <PlanEditor />
  if (id) return <PlanDetail id={id} offer={offer} />
  return <PlanList />
}

function PlanList() {
  const resource = useAdminResource(signal => adminMembershipPlans.list(signal), 'admin-membership-plans')
  return <><PageHeader title="Membership Plans" subtitle="Manage Multi-Gym pricing, availability and promotions." action={<Link to={`${basePath}/new`} className="fg-button fg-button--primary"><Icon name="plus" size={18} />Create Plan</Link>} />
    <PaymentNotice /><Resource resource={resource}>{catalog => <>
      <div className="ad-plan-toolbar"><p>{catalog.items.length} configured plans · In backend display order</p><Button variant="secondary" onClick={resource.retry}>Refresh plans</Button></div>
      {!catalog.items.length ? <EmptyState title="No Multi-Gym plans yet" description="Create a plan to configure pricing. Payment remains disabled." action={<Link to={`${basePath}/new`} className="fg-button fg-button--primary">Create Plan</Link>} /> : <div className="ad-plan-grid">{catalog.items.map(plan => <DataCard key={plan.id} title={plan.name} action={<StatusBadge status={plan.is_active ? 'ACTIVE' : 'INACTIVE'} />}>
        <p className="ad-plan-meta">{planDuration(plan)} · Display order {plan.display_order}</p>
        <PlanPrice plan={plan} />
        <p className="ad-plan-meta">{plan.offer?.title || (plan.offer ? 'Offer active' : 'No effective discount right now')}</p>
        {plan.badge && <p>Customer badge: <strong>{plan.badge}</strong></p>}
        <div className="ad-plan-links"><Link to={`${basePath}/${plan.id}`} className="fg-button fg-button--secondary" label={`Edit ${plan.name}`}>Edit Plan</Link><Link to={`${basePath}/${plan.id}/offer`} className="fg-button fg-button--text" label={`Manage offer for ${plan.name}`}>Manage Offer</Link></div>
      </DataCard>)}</div>}
    </>}</Resource></>
}

function PlanDetail({ id, offer }: { id: number; offer: boolean }) {
  const resource = useAdminResource(signal => adminMembershipPlans.detail(id, signal), `admin-plan:${id}`)
  return <Resource resource={resource}>{detail => offer ? <OfferEditor key={`${id}:${detail.plan.version}`} detail={detail} reload={resource.retry} /> : <PlanEditor key={`${id}:${detail.plan.version}`} detail={detail} reload={resource.retry} />}</Resource>
}
function PaymentNotice() { return <Alert>Controlled MVP: membership checkout uses wallet test credits in development only. External payments remain disabled. Configure eligible partner gyms from Gym details. Pause policy changes apply to future requests; accepted pauses remain honored.</Alert> }
function PlanPrice({ plan }: { plan: PlatformPlan }) {
  return <div className="ad-plan-price">{plan.offer && <del>{money(plan.base_price, plan.currency)}</del>}<strong>{money(plan.final_price, plan.currency)}</strong><small>Current backend price{plan.offer && ` · ${plan.discount_percentage !== null ? `${Number(plan.discount_percentage)}% off` : `Save ${money(plan.discount_amount, plan.currency)}`}`}</small></div>
}
function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="ad-field"><span>{label}</span>{children}</label> }

function SaveDialog({ title, children, onClose, save, onSaved }: { title: string; children: ReactNode; onClose: () => void; save: () => Promise<unknown>; onSaved: () => void }) {
  const mutation = useMutation()
  return <Modal title={title} onClose={() => { if (!mutation.pending) onClose() }}><p>{children}</p>{mutation.error && <Alert tone="danger">{mutation.error}</Alert>}
    <div className="ad-dialog-actions"><Button variant="secondary" disabled={mutation.pending} onClick={onClose}>{mutation.error ? 'Back to editor' : 'Keep unchanged'}</Button><Button loading={mutation.pending} onClick={() => void mutation.run(async () => { try { await save() } catch (error) { throw new Error(planAdminError(error)) } onSaved() })}>Confirm Save</Button></div>
  </Modal>
}
function Reload({ action }: { action: () => void }) {
  const [confirm, setConfirm] = useState(false)
  return <><Button variant="secondary" onClick={() => setConfirm(true)}>Reload latest version</Button>{confirm && <Modal title="Discard unsaved changes?" onClose={() => setConfirm(false)}><p>Reloading replaces your form with the latest saved configuration.</p><div className="ad-dialog-actions"><Button variant="secondary" onClick={() => setConfirm(false)}>Keep editing</Button><Button onClick={action}>Discard and reload</Button></div></Modal>}</>
}

function PlanEditor({ detail, reload }: { detail?: AdminPlanDetail; reload?: () => void }) {
  const plan = detail?.plan
  const [form, setForm] = useState<PlanInput>(() => plan ? editablePlan(plan) : { code: '', name: '', description: null, duration_value: 1, duration_unit: 'MONTH', base_price: '', currency: 'INR', benefits: [], badge: null, display_order: 0, is_active: false })
  const [benefits, setBenefits] = useState(form.benefits.join('\n'))
  const [error, setError] = useState('')
  const [pending, setPending] = useState<PlanInput | null>(null)
  const toast = useToast(); const errorId = useId()
  const change = <K extends keyof PlanInput>(key: K, value: PlanInput[K]) => setForm(current => ({ ...current, [key]: value }))
  return <><PageHeader title={plan ? 'Edit Membership Plan' : 'Create Membership Plan'} subtitle={plan ? `${plan.name} · Version ${plan.version}` : 'Configure a Multi-Gym plan. New plans start inactive.'} back={{ to: basePath, label: 'Membership Plans' }} action={reload && <Reload action={reload} />} /><PaymentNotice />
    <div className="ad-plan-editor"><DataCard title="Plan configuration"><form className="ad-plan-form" aria-describedby={error ? errorId : undefined} onSubmit={event => {
      event.preventDefault(); setError('')
      const lines = benefits.split('\n').map(value => value.trim()).filter(Boolean)
      if (lines.length > 20 || lines.some(value => value.length > 250)) { setError('Use at most 20 benefits, with up to 250 characters each.'); return }
      setPending({ ...form, name: form.name.trim(), description: form.description?.trim() || null, badge: form.badge?.trim() || null, benefits: lines })
    }}>
      <fieldset className="ad-plan-fields"><legend className="srOnly">Plan details</legend>
        <Field label="Plan name"><input name="name" required minLength={2} maxLength={120} value={form.name} onChange={e => change('name', e.target.value)} /></Field>
        <Field label="Unique plan code"><input name="code" required minLength={2} maxLength={80} pattern="[a-z0-9][a-z0-9-]+" value={form.code} onChange={e => change('code', e.target.value)} /><small>Lowercase letters, numbers and hyphens.</small></Field>
        <Field label="Base price (INR)"><input name="base_price" type="number" inputMode="decimal" min="0" max="9999999999.99" step="0.01" required value={form.base_price} onChange={e => change('base_price', e.target.value)} /><small>Offers are calculated separately by the backend.</small></Field>
        <Field label="Currency"><input value="INR" readOnly /></Field>
        <Field label="Duration value"><input name="duration_value" type="number" min={1} max={3660} step={1} required value={form.duration_value || ''} onChange={e => change('duration_value', Number(e.target.value))} /></Field>
        <Field label="Duration unit"><select name="duration_unit" value={form.duration_unit} onChange={e => change('duration_unit', e.target.value as PlanInput['duration_unit'])}><option value="DAY">Days</option><option value="MONTH">Months</option><option value="YEAR">Years</option></select></Field>
        <Field label="Display order"><input name="display_order" type="number" min={0} max={100000} step={1} required value={form.display_order} onChange={e => change('display_order', Number(e.target.value))} /><small>Lower values appear first.</small></Field>
        <Field label="Promotional badge (optional)"><input name="badge" maxLength={60} value={form.badge || ''} onChange={e => change('badge', e.target.value || null)} /></Field>
      </fieldset>
      <Field label="Description (optional)"><textarea name="description" rows={3} maxLength={2000} value={form.description || ''} onChange={e => change('description', e.target.value || null)} /></Field>
      <Field label="Benefits (one per line)"><textarea name="benefits" rows={4} maxLength={5020} value={benefits} onChange={e => setBenefits(e.target.value)} /><small>Only describe supported benefits.</small></Field>
      <fieldset className="ad-plan-fields"><legend>Pause policy</legend>
        <label className="ad-plan-checkbox"><input name="pause_allowed" type="checkbox" checked={form.pause_rule?.allowed ?? false} onChange={e => change('pause_rule', { allowed: e.target.checked, max_pause_days: e.target.checked ? form.pause_rule?.max_pause_days || 0 : 0 })} /><span>Allow Pause</span></label>
        <Field label="Maximum pause days"><input name="max_pause_days" type="number" min={1} step={1} required={form.pause_rule?.allowed} disabled={!form.pause_rule?.allowed} value={form.pause_rule?.max_pause_days || ''} onChange={e => change('pause_rule', { allowed: true, max_pause_days: Number(e.target.value) })} /></Field>
      </fieldset>
      <label className="ad-plan-checkbox"><input name="is_active" type="checkbox" checked={form.is_active} onChange={e => change('is_active', e.target.checked)} /><span>Visible in the customer catalog</span></label>
      <p className="ad-plan-meta">Hiding a plan prevents new selections. Existing memberships are not changed.</p>
      {error && <div id={errorId}><Alert tone="danger">{error}</Alert></div>}
      <div className="ad-plan-links"><Button type="submit">{plan ? 'Review Changes' : 'Review New Plan'}</Button><Link to={basePath} className="fg-button fg-button--secondary">Back to Plans</Link></div>
    </form></DataCard>
    {plan && <DataCard title="Currently saved price"><PlanPrice plan={plan} /><p className="ad-plan-meta">This is the saved backend price, not a prediction of unsaved changes.</p><Link to={`${basePath}/${plan.id}/offer`} className="fg-button fg-button--secondary">Manage Offer</Link></DataCard>}</div>
    {pending && <SaveDialog title={plan ? 'Save plan changes?' : 'Create this plan?'} onClose={() => setPending(null)} save={() => plan ? adminMembershipPlans.update(plan.id, pending, plan.version) : adminMembershipPlans.create(pending)} onSaved={() => { toast(plan ? 'Membership plan updated.' : 'Membership plan created.'); navigate(basePath) }}>
      {pending.name}: base price {money(pending.base_price, pending.currency)}. The plan will be {pending.is_active ? 'visible' : 'hidden'} in the customer catalog. External payments remain disabled; development checkout uses test credits.
    </SaveDialog>}
  </>
}

function OfferEditor({ detail, reload }: { detail: AdminPlanDetail; reload: () => void }) {
  const { plan, offer_configuration: existing } = detail
  const [kind, setKind] = useState<OfferInput['kind']>(existing?.kind || 'PERCENTAGE')
  const [value, setValue] = useState(existing?.value || '')
  const [title, setTitle] = useState(existing?.title || '')
  const [start, setStart] = useState(existing ? utcInput(existing.starts_at) : '')
  const [end, setEnd] = useState(existing ? utcInput(existing.ends_at) : '')
  const [enabled, setEnabled] = useState(existing?.is_active || false)
  const [error, setError] = useState(''); const [pending, setPending] = useState<OfferInput | null>(null)
  const toast = useToast(); const errorId = useId()
  return <><PageHeader title="Manage Offer" subtitle={`${plan.name} · Version ${plan.version}`} back={{ to: basePath, label: 'Membership Plans' }} action={<Reload action={reload} />} /><PaymentNotice />
    <div className="ad-plan-editor"><DataCard title={existing ? 'Offer configuration' : 'Add an offer'} action={existing && <StatusBadge status={existing.state} />}>
      <form className="ad-plan-form" aria-describedby={error ? errorId : undefined} onSubmit={event => {
        event.preventDefault(); setError('')
        if (Date.parse(`${end}Z`) <= Date.parse(`${start}Z`)) { setError('Offer end must be after its start. All times are UTC.'); return }
        setPending({ expected_version: plan.version, kind, value, title: title.trim() || null, starts_at: utcValue(start), ends_at: utcValue(end), is_active: enabled })
      }}>
        <p>One configured offer per plan. Saving replaces the previous offer settings; discounts do not stack.</p>
        <fieldset className="ad-plan-fields"><legend className="srOnly">Offer settings</legend>
          <Field label="Discount type"><select name="kind" value={kind} onChange={e => setKind(e.target.value as OfferInput['kind'])}><option value="PERCENTAGE">Percentage off</option><option value="FIXED">Fixed amount off</option></select></Field>
          <Field label={kind === 'PERCENTAGE' ? 'Discount percentage' : 'Discount amount (INR)'}><input name="value" type="number" inputMode="decimal" min="0.01" max={kind === 'PERCENTAGE' ? '100' : '9999999999.99'} step="0.01" required value={value} onChange={e => setValue(e.target.value)} /></Field>
          <Field label="Starts at (UTC)"><input name="starts_at" type="datetime-local" step="1" required value={start} onChange={e => setStart(e.target.value)} /></Field>
          <Field label="Ends at (UTC)"><input name="ends_at" type="datetime-local" step="1" required value={end} onChange={e => setEnd(e.target.value)} /></Field>
        </fieldset>
        <p className="ad-plan-meta">Enter UTC, not your device’s local time. India Standard Time is UTC +05:30. The backend decides when the offer takes effect and expires.</p>
        <Field label="Offer title (optional)"><input name="title" maxLength={120} value={title} onChange={e => setTitle(e.target.value)} /></Field>
        <label className="ad-plan-checkbox"><input name="is_active" type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} /><span>Enable offer during its scheduled dates</span></label>
        {!plan.is_active && <Alert tone="warning">This plan is hidden. An enabled offer does not make the plan visible.</Alert>}
        {error && <div id={errorId}><Alert tone="danger">{error}</Alert></div>}
        <div className="ad-plan-links"><Button type="submit">Review Offer</Button>{existing?.is_active && <Button variant="danger" onClick={() => setPending({ expected_version: plan.version, kind: existing.kind, value: existing.value, title: existing.title, starts_at: existing.starts_at, ends_at: existing.ends_at, is_active: false })}>Disable Offer</Button>}</div>
      </form>
    </DataCard><DataCard title="Currently saved price"><PlanPrice plan={plan} /><p className="ad-plan-meta">Final prices are calculated only by the backend. Save and reload to see the effective result.</p><Link to={`${basePath}/${plan.id}`} className="fg-button fg-button--secondary">Edit Plan</Link></DataCard></div>
    {pending && <SaveDialog title={pending.is_active ? 'Save this offer?' : 'Save disabled offer?'} onClose={() => setPending(null)} save={() => adminMembershipPlans.offer(plan.id, pending)} onSaved={() => { toast(pending.is_active ? 'Offer saved. The backend controls its schedule.' : 'Offer disabled.'); setPending(null); reload() }}>
      {pending.kind === 'PERCENTAGE' ? `${pending.value}% off` : `${money(pending.value, plan.currency)} off`}. {pending.is_active ? `Scheduled from ${utcInput(pending.starts_at).replace('T', ' ')} to ${utcInput(pending.ends_at).replace('T', ' ')} UTC.` : 'The offer will not apply to customer prices.'} External payments remain disabled.
    </SaveDialog>}
  </>
}