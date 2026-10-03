import { useState } from 'react'
import { Alert, Button, Link, Modal } from '../common/UI'
import { useMutation } from '../../hooks/useResource'
import { money } from '../../services/client'
import { MembershipNotice } from './MembershipUI'

export function TestCreditNotice() { return <MembershipNotice warning>Controlled MVP · Test credits only. No bank, card or external payment is taken. Wallet credits are for testing and are not verified real-money funds.</MembershipNotice> }

export default function WalletMembershipPayment({ amount, currency, balance, walletCurrency, available, pay, refresh }: {
  amount: string; currency: string; balance: string; walletCurrency: string; available: boolean
  pay: () => Promise<void>; refresh: () => void
}) {
  const [confirm, setConfirm] = useState(false)
  const mutation = useMutation()
  return <div className="fg-stack"><TestCreditNotice /><p>Wallet balance: <strong>{money(balance, walletCurrency)}</strong></p>
    <Button disabled={!available || mutation.pending} onClick={() => setConfirm(true)}>{available ? `Pay with Wallet · ${money(amount, currency)}` : 'Wallet payment unavailable'}</Button>
    <Button variant="secondary" disabled={mutation.pending} onClick={refresh}>Refresh current price and balance</Button>
    <Link to={`/wallet/recharge?returnTo=${encodeURIComponent(window.location.pathname + window.location.search)}`} className="fg-inline-link">Add test credits</Link>
    {confirm && <Modal title="Pay with test credits?" onClose={() => { if (!mutation.pending) setConfirm(false) }}><p>Use {money(amount, currency)} of wallet test credits to activate this membership? The backend will revalidate the price and eligibility.</p>
      {mutation.error && <Alert>{mutation.error}</Alert>}
      <div className="fm-card-actions"><Button variant="secondary" disabled={mutation.pending} onClick={() => setConfirm(false)}>Back to review</Button><Button disabled={!!mutation.error} loading={mutation.pending} onClick={() => void mutation.run(async () => { await pay(); setConfirm(false) })}>Confirm Wallet Payment</Button></div>
      {mutation.error && <Button variant="text" onClick={() => { setConfirm(false); mutation.setError(''); refresh() }}>Refresh checkout</Button>}
    </Modal>}
  </div>
}