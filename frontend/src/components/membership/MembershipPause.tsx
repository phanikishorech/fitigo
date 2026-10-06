import { useRef, useState } from 'react'
import { useMembershipResource } from '../../hooks/useMembershipResource'
import { membershipPauseService, type PauseEligibility, type PausePreview } from '../../services/membershipPauseService'
import { ApiError } from '../../services/client'
import { Alert, Button, Modal } from '../common/UI'
import Icon from '../common/Icon'
import { MembershipFacts, MembershipNotice, MembershipResource, MembershipStatusBadge } from './MembershipUI'
import { membershipDate } from '../../utils/membership'
import { clearReadCache } from '../../services/readCache'

export function MembershipPause({ membershipId, onChanged }: { membershipId: number; onChanged: () => void }) {
  const resource = useMembershipResource(() => membershipPauseService.eligibility(membershipId), `pause:${membershipId}`)
  const [open, setOpen] = useState(false)
  return <section className="fm-pause-section" aria-label="Membership pause">
    <div className="fm-pause-heading"><span className="fm-icon"><Icon name="clock" size={23} /></span><div><h3>Membership pause</h3><p className="fm-muted">Your pause allowance, dates and history.</p></div></div>
    <MembershipResource resource={resource}>{eligibility => <>
    <MembershipFacts rows={[
      ['Original expiry', membershipDate(eligibility.original_end_at)], ['Current expiry', membershipDate(eligibility.current_end_at)],
      ['Pause days reserved / used', `${eligibility.pause_days_used} / ${eligibility.max_pause_days}`],
      ['Pause allowance remaining', `${eligibility.pause_days_remaining} days`],
    ]} />
    {eligibility.currently_paused && eligibility.current_pause ? <MembershipNotice warning><strong>Membership Paused</strong><p>Paused until {membershipDate(eligibility.current_pause.end_date)}. Resumes {membershipDate(eligibility.current_pause.resumes_on)}.</p><p>Gym access is unavailable. Daily access is not consumed during the pause.</p></MembershipNotice> : !eligibility.can_pause && <div className="fm-pause-unavailable"><Icon name="help" size={19} /><p>{eligibility.reason_code === 'PAUSE_NOT_ALLOWED' ? 'Pause unavailable for this membership plan.' : eligibility.reason_code === 'PAUSE_LIMIT_EXCEEDED' ? 'You have used your pause allowance for this plan.' : 'Pause is not available for this membership right now.'}</p></div>}
    {eligibility.history.length > 0 && <details className="fm-pause-history"><summary>Pause History</summary>{eligibility.history.map(period => <div key={period.id} className="fm-pause-period"><MembershipStatusBadge status={period.status} /><p>{membershipDate(period.start_date)} – {membershipDate(period.end_date)} · {period.days} days</p><small>Resumes {membershipDate(period.resumes_on)}</small></div>)}</details>}
    <div className="fm-card-actions">{!(eligibility.currently_paused && eligibility.current_pause) && eligibility.can_pause && <Button variant="secondary" onClick={() => setOpen(true)}>Pause Membership</Button>}<Button variant="text" onClick={resource.retry}>Refresh pause policy</Button></div>
    {open && <PauseDialog eligibility={eligibility} onClose={() => setOpen(false)} onSaved={() => { setOpen(false); resource.retry(); onChanged() }} />}
  </>}</MembershipResource></section>
}

function PauseDialog({ eligibility, onClose, onSaved }: { eligibility: PauseEligibility; onClose: () => void; onSaved: () => void }) {
  const [start, setStart] = useState(eligibility.eligible_from || '')
  const [days, setDays] = useState('')
  const [preview, setPreview] = useState<PausePreview | null>(null)
  const [saved, setSaved] = useState<PauseEligibility | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const lock = useRef(false)
  const requestKey = useRef(crypto.randomUUID())
  async function run(confirm: boolean) {
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    try {
      if (confirm && preview) {
        const result = await membershipPauseService.confirm(eligibility.membership_id, preview, requestKey.current)
        clearReadCache()
        setSaved(result)
      } else {
        const result = await membershipPauseService.preview(eligibility.membership_id, { start_date: start, days: Number(days) })
        setPreview(result)
      }
    } catch (e) {
      setError(e instanceof ApiError && e.code ? e.message : 'Unable to pause your membership. Please try again.')
      // Do not change preview or key after a technical failure: retry must replay
      // the SAME request in case the server committed before the response was lost.
      if (e instanceof ApiError && e.code && e.code !== 'IDEMPOTENCY_CONFLICT') setPreview(null)
    } finally { lock.current = false; setBusy(false) }
  }
  const close = () => { if (!lock.current) saved ? onSaved() : onClose() }
  return <Modal title={saved ? 'Pause scheduled' : preview ? 'Confirm Pause' : 'Pause Membership'} onClose={close}>
    {saved && preview ? <div className="fm-page"><MembershipNotice>Your pause has been saved. Your membership remains active until the scheduled pause begins.</MembershipNotice><MembershipFacts rows={[
      ['Paused period', `${membershipDate(preview.start_date)} – ${membershipDate(preview.end_date)}`], ['Resumes', membershipDate(preview.resumes_on)],
      ['Membership expiry', membershipDate(saved.current_end_at)], ['Pause allowance remaining', `${saved.pause_days_remaining} days`],
    ]} /><Button onClick={onSaved}>View Membership</Button></div> : <form className="fm-page fm-stack" onSubmit={e => { e.preventDefault(); void run(!!preview) }}>
      <p>You have {eligibility.pause_days_remaining} pause days remaining. Dates use {eligibility.timezone}.</p>
      {!preview ? <><label className="fg-field">Start date<input name="pause_start" type="date" required min={eligibility.eligible_from || undefined} max={eligibility.eligible_until || undefined} value={start} disabled={busy} onChange={e => { setStart(e.target.value); requestKey.current = crypto.randomUUID() }} /></label>
        <label className="fg-field">Pause for (days)<input name="pause_days" type="number" step={1} min={1} max={eligibility.pause_days_remaining} required value={days} disabled={busy} onChange={e => { setDays(e.target.value); requestKey.current = crypto.randomUUID() }} /></label>
        <p className="fm-muted">Choose future dates in the available range. FitiGo checks overlapping pauses and calculates your updated expiry before confirmation.</p>
      </> : <MembershipFacts rows={[
        ['Pause period', `${membershipDate(preview.start_date)} – ${membershipDate(preview.end_date)}`], ['Duration', `${preview.days} days`], ['Resumes', membershipDate(preview.resumes_on)],
        ['Current expiry', membershipDate(preview.current_end_at)], ['New expiry', membershipDate(preview.new_end_at)], ['Remaining after pause', `${preview.pause_days_remaining_after} days`],
      ]} />}
      <MembershipNotice>During paused dates, membership gym access and QR are unavailable. Daily access is not consumed. Your membership resumes automatically.</MembershipNotice>
      {error && <Alert>{error}<Button variant="text" disabled={busy} onClick={onSaved}>Refresh membership and allowance</Button></Alert>}
      <div className="fm-card-actions"><Button variant="secondary" disabled={busy} onClick={preview ? () => setPreview(null) : close}>{preview ? 'Edit dates' : 'Cancel'}</Button><Button type="submit" loading={busy}>{preview ? 'Confirm Pause' : 'Review Pause'}</Button></div>
    </form>}
  </Modal>
}