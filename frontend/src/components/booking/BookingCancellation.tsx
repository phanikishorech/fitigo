import { useState } from 'react'
import { bookingService } from '../../services/bookingService'
import { useMutation } from '../../hooks/useResource'
import { money } from '../../services/client'
import { istDateTime } from '../../utils/membership'
import { Alert, Button, Link, Modal } from '../common/UI'
import { notifyActivity } from '../../services/customerActivity'

export type CancellationPolicy = { eligible: boolean; reason: string; policy: string; deadline: string | null; scheduled_start: string | null; refundable_amount: string; currency: string; wallet_credit_amount: string; wallet_transaction_id: number | null; cancelled_at: string | null; cancellation_reason: string | null }

export function CancellationResult({ policy }: { policy?: CancellationPolicy | null }) {
  if (!policy?.cancelled_at) return null
  return <div className="fg-stack"><p>Cancelled: {istDateTime(policy.cancelled_at)}</p><p>Wallet credit: {money(policy.wallet_credit_amount, policy.currency)}</p>{policy.wallet_transaction_id && <small>Wallet transaction #{policy.wallet_transaction_id}</small>}{policy.cancellation_reason && <p>Reason: {policy.cancellation_reason}</p>}</div>
}

export default function BookingCancellation({ id, policy, onChanged }: { id: number; policy?: CancellationPolicy | null; onChanged: () => void }) {
  const [open, setOpen] = useState(false), [reason, setReason] = useState(''), [success, setSuccess] = useState('')
  const mutation = useMutation()
  if (!policy) return <p className="fg-muted">Cancellation eligibility is unavailable. Refresh to check the current policy.</p>
  return <div className="fg-stack"><CancellationResult policy={policy} />{success && <p role="status">{success} <Link to="/wallet">View wallet</Link></p>}{!policy.cancelled_at && <><p className="fg-muted">{policy.policy}</p>{policy.deadline && <small>Cancellation deadline: {istDateTime(policy.deadline)}</small>}{policy.eligible ? <Button variant="danger" onClick={() => { mutation.setError(''); setOpen(true) }}>Cancel Booking</Button> : <p className="fg-muted">{policy.reason}</p>}</>}{open && <Modal title="Cancel Booking?" onClose={() => { if (!mutation.pending) setOpen(false) }}><div className="fg-stack"><p>This action cannot be undone. Cancellation must complete by {policy.deadline ? istDateTime(policy.deadline) : 'the server-confirmed deadline'}.</p><p>Eligible credit: <strong>{money(policy.refundable_amount, policy.currency)}</strong> to FitiGo Wallet only—not your original payment method. Eligibility is checked again when you confirm.</p><label className="fg-field">Reason (optional)<textarea maxLength={500} value={reason} onChange={event => setReason(event.target.value)} /></label>{mutation.error && <Alert>{mutation.error}</Alert>}<Button variant="danger" loading={mutation.pending} onClick={() => void mutation.run(async () => { const result = await bookingService.cancel(id, reason.trim() || undefined); setOpen(false); setSuccess(`Booking cancelled. Wallet credit: ${money(result.cancellation?.wallet_credit_amount || '0', result.currency)}.`); notifyActivity('notifications'); onChanged() })}>Confirm cancellation</Button><Button variant="secondary" disabled={mutation.pending} onClick={() => setOpen(false)}>Keep booking</Button></div></Modal>}</div>
}