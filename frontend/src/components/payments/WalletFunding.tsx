import { useEffect, useState } from 'react'
import { paymentService, type PaymentSource, type FundingQuote } from '../../services/paymentService'
import { money } from '../../services/client'
import { Alert, Button } from '../common/UI'

export default function WalletFunding({ source, disabled, onChange }: { source: PaymentSource; disabled: boolean; onChange: (selection: { use_wallet: boolean; wallet_amount?: string }, ready: boolean) => void }) {
  const [useWallet, setUseWallet] = useState(false), [requested, setRequested] = useState('')
  const [quote, setQuote] = useState<FundingQuote | null>(null), [error, setError] = useState(''), [retry, setRetry] = useState(0)
  const sourceKey = JSON.stringify(source)
  useEffect(() => {
    let alive = true
    onChange({ use_wallet: useWallet, ...(useWallet && requested ? { wallet_amount: requested } : {}) }, false)
    setQuote(null); setError('')
    const timer = setTimeout(() => {
      void paymentService.quote({ ...source, use_wallet: useWallet, ...(useWallet && requested ? { wallet_amount: requested } : {}) }).then(value => {
        if (!alive) return
        setQuote(value); onChange({ use_wallet: useWallet, ...(useWallet && requested ? { wallet_amount: requested } : {}) }, true)
      }).catch(reason => { if (alive) setError(reason.message || 'Unable to calculate payment amounts.') })
    }, 200)
    return () => { alive = false; clearTimeout(timer) }
  }, [sourceKey, useWallet, requested, retry])
  return <section className="fg-stack" aria-label="Payment method"><h3>Payment method</h3><label className="fg-checkbox"><input type="checkbox" checked={useWallet} disabled={disabled || (!useWallet && (!quote || Number(quote.available_wallet_balance) <= 0))} onChange={event => setUseWallet(event.target.checked)} />Use FitiGo Wallet</label>{error ? <><Alert>{error}</Alert><Button variant="secondary" onClick={() => setRetry(value => value + 1)}>Retry payment breakdown</Button></> : !quote ? <p role="status">Calculating payment breakdown…</p> : <><p>FitiGo Wallet balance: {money(quote.wallet_balance)}</p><p>Available balance: {money(quote.available_wallet_balance)}{Number(quote.reserved_balance) > 0 && ` · Reserved: ${money(quote.reserved_balance)}`}</p>{quote.wallet_unavailable_reason && <small>{quote.wallet_unavailable_reason}</small>}{useWallet && <label className="fg-field">Wallet contribution limit (optional)<input type="number" min="0" step="0.01" max={quote.available_wallet_balance} placeholder="Use maximum available" value={requested} disabled={disabled} onChange={event => setRequested(event.target.value)} /><small>Leave blank to apply the maximum eligible balance.</small></label>}<div className="fg-stack" role="status"><div className="fg-total-row"><span>Total payable</span><strong>{money(quote.total_amount)}</strong></div><div className="fg-total-row"><span>Wallet contribution</span><strong>{money(quote.wallet_amount)}</strong></div><div className="fg-total-row"><span>Amount payable online</span><strong>{money(quote.gateway_amount)}</strong></div><small>{Number(quote.gateway_amount) === 0 ? 'Wallet-only: no external payment window will open.' : `Remaining payment through ${quote.provider === 'CASHFREE' ? 'Cashfree' : 'Razorpay'}.`} Final amounts are revalidated before checkout.</small></div></>}</section>
}