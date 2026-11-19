import { useState } from 'react'
import { useResource } from '../../hooks/useResource'
import { walletService } from '../../services/accountService'
import { paymentService } from '../../services/paymentService'
import { dateLabel, money } from '../../services/client'
import { Alert, Button, EmptyState, ErrorState, Heading, Link, Skeleton } from '../../components/common/UI'
import GatewayPayment from '../../components/common/GatewayPayment'

export default function WalletPage({ recharge = false }: { recharge?: boolean }) {
  const wallet = useResource(walletService.transactions, 'wallet')
  const config = useResource(paymentService.config, 'wallet-gateway')
  const [amount, setAmount] = useState('1000')
  const [review, setReview] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const valid = /^\d+(\.\d{1,2})?$/.test(amount) && Number(amount) >= 1 && Number(amount) <= 100000
  return <><Heading title={recharge ? 'Recharge your wallet' : 'FitiGo wallet'} subtitle="Recharge securely through your configured payment gateway." /><div className="fg-two-column"><div className="fg-stack">
    {wallet.loading ? <Skeleton cards={1} /> : wallet.error ? <ErrorState message={wallet.error} retry={wallet.retry} /> : <>
      <div className="fg-wallet-card">
        <p>Wallet balance</p>
        <strong className="fg-price">{money(wallet.data!.balance, wallet.data!.currency)}</strong>
        <p>Available to spend: {wallet.data!.available_balance == null ? 'Not available' : money(wallet.data!.available_balance, wallet.data!.currency)}</p>
        <p>Reserved for pending payments: {money(wallet.data!.reserved_balance || '0', wallet.data!.currency)}</p>
        <Link to="/wallet/recharge" className="fg-button fg-button--secondary">Recharge wallet</Link>
      </div>
      {wallet.data!.wallet_unavailable_reason && <section className="fg-panel fg-stack" role="status" aria-label="Wallet spending status">
        <h2>Wallet spending unavailable</h2>
        <p>{wallet.data!.wallet_unavailable_reason}</p>
        <p>Your recorded wallet balance is shown above. Recharging does not remove a spending restriction.</p>
        <Button variant="secondary" onClick={wallet.retry}>Refresh wallet</Button>
      </section>}
    </>}
    {success && <p role="status" className="fg-success">Payment verified and wallet credited. <Link to="/wallet">View wallet</Link></p>}
    {recharge && <section className="fg-panel fg-stack"><h2>Add to your balance</h2>{config.loading ? <Skeleton cards={1} /> : config.error ? <ErrorState message={config.error} retry={config.retry} /> : !config.data?.enabled ? <Alert>Payment gateway is unavailable. No credit has been added.</Alert> : <>
      <p>{config.data.mode === 'test' ? 'Test mode: sandbox payment, no real money. Credits cannot be mixed with a live wallet.' : 'Live mode: real gateway payment.'}</p>
      {review === null ? <><div className="fg-facility-options">{[500, 1000, 2000, 5000].map(value => <Button key={value} variant={amount === String(value) ? 'primary' : 'secondary'} onClick={() => setAmount(String(value))}>{money(value)}</Button>)}</div><label className="fg-field">Recharge amount (INR)<input type="number" min="1" max="100000" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} /></label><Button disabled={!valid} onClick={() => setReview(Number(amount).toFixed(2))}>Review secure recharge</Button></> : <><h3>{money(review)}</h3><GatewayPayment source={{ kind: 'WALLET_TOPUP', amount: review }} onPaid={() => { setSuccess(true); wallet.retry() }} /><p className="fg-muted">If interrupted, resume the existing recharge in payment history. Do not create another payment.</p></>}
    </>}</section>}
  </div><section className="fg-panel fg-stack"><h2>Wallet ledger</h2>{wallet.data?.reservations?.map(hold => <div className="fg-list-row" key={hold.checkout_id}><span><strong>Wallet reservation &middot; {hold.state.toLowerCase()}</strong><small>{dateLabel(hold.created_at)} &middot; {hold.checkout_id}</small></span><span>{money(hold.amount, hold.currency)}</span></div>)}{wallet.data?.reservations?.length ? <small>Reservations are not additional charges. A completed payment appears once in the ledger below.</small> : null}<Link to="/profile/payments" className="fg-inline-link">All payments, failures and refunds</Link><p className="fg-muted">Latest 100 wallet entries. A gateway recharge appears only after verified success.</p>{wallet.data?.transactions.length ? wallet.data.transactions.map(row => <div className="fg-list-row" key={row.id}><span><strong>{row.description || row.txn_type}</strong><small>{dateLabel(row.created_at)} · {row.txn_type} · #{row.id}</small></span><strong>{row.direction === 'IN' ? '+' : '−'}{money(row.amount, row.currency)}</strong></div>) : !wallet.loading && <EmptyState title="No wallet transactions yet" />}</section></div></>
}