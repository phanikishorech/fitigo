import { useRef, useState } from 'react'
import { useMutation, useResource } from '../../hooks/useResource'
import { dateLabel, request, money } from '../../services/client'
import { paymentService, type PaymentCheckout } from '../../services/paymentService'
import GatewayPayment from '../../components/common/GatewayPayment'
import Icon from '../../components/common/Icon'
import { Alert, Button, EmptyState, ErrorState, Link, Modal, Skeleton } from '../../components/common/UI'
import { istDateTime } from '../../utils/membership'
import { historyAction, historyStatus, historyStatuses, paymentHistoryNotice, purchasePresentation, purchaseTypes, readablePayment } from '../../utils/paymentHistory'
import './paymentHistory.css'

type PaymentRow = {
  id: string; source: string; kind: string; status: string; amount: string; currency: string
  provider: string; mode: string | null; created_at: string; updated_at?: string
  checkout_id: string | null; provider_order_id: string | null; transaction_id: string | null
  failure_code: string | null; order_details: Record<string, string | number | null> | null
  bookings: { id: number; date?: string; status?: string; amount?: string; quantity?: number; currency?: string }[]
  membership_ids: number[]
  attempts: { transaction_id: string; status: string; amount: string; currency?: string; refunded_amount: string; first_seen_at: string; updated_at: string }[]
  wallet_entries: { id: number; direction: string; type: string; amount: string }[]
}

function PaymentBadge({ status }: { status: string }) {
  const badge = historyStatus(status)
  return <span className={`ph-status ph-status--${badge.tone}`}><Icon name={badge.icon} size={13} />{badge.label}</span>
}

function PaymentCard({ row, pending, onManage }: { row: PaymentRow; pending: boolean; onManage: () => void }) {
  const purchase = purchasePresentation(row.kind)
  const notice = paymentHistoryNotice(row.status, row.failure_code)
  const planName = row.order_details?.name
  const description = typeof planName === 'string' && planName.trim() ? planName : row.bookings.length
    ? `${row.bookings.length} ${row.bookings.length === 1 ? 'booking' : 'bookings'}`
    : row.kind === 'WALLET_TOPUP' ? 'Gateway wallet recharge' : 'Gateway purchase'
  return <article className="ph-card" aria-label={`${purchase.label} · ${historyStatus(row.status).label} · ${money(row.amount, row.currency)}`}>
    <div className="ph-card-top">
      <span className="ph-purchase-icon"><Icon name={purchase.icon} size={23} /></span>
      <div className="ph-purchase"><h3>{purchase.label}</h3><p>{description}</p></div>
      <div className="ph-amount"><strong>{money(row.amount, row.currency)}</strong><PaymentBadge status={row.status} /></div>
    </div>
    <div className="ph-meta"><span><Icon name="calendar" size={14} /><span>Created {istDateTime(row.created_at)}</span></span><span className="ph-provider">{row.provider === 'RAZORPAY' ? 'Razorpay' : row.provider === 'CASHFREE' ? 'Cashfree' : row.provider}</span><span className={`ph-mode ${row.mode === 'test' ? 'ph-mode--test' : ''}`}>{row.mode === 'test' ? 'Test · no real money' : row.mode === 'live' ? 'Live payment' : 'Mode not recorded'}</span></div>
    {notice && <div className="ph-notice"><Icon name="help" size={18} /><p>{notice}</p></div>}
    <details className="ph-details"><summary><span><Icon name="ticket" size={16} />Transaction and order details</span><Icon name="down" size={16} /></summary>
      <div className="ph-detail-content">
        <section aria-label="Payment references"><h4>Payment references</h4><dl className="ph-reference-grid">
          <div><dt>Internal reference</dt><dd>{row.id}</dd></div>
          <div><dt>Provider order</dt><dd>{row.provider_order_id || 'Not available'}</dd></div>
          <div><dt>Transaction</dt><dd>{row.transaction_id || 'Not available'}</dd></div>
          <div><dt>Failure / review code</dt><dd>{row.failure_code || 'None recorded'}</dd></div>
          {row.updated_at && <div><dt>Record last updated</dt><dd>{istDateTime(row.updated_at)}</dd></div>}
        </dl></section>
        {row.order_details && Object.values(row.order_details).some(value => value !== null) && <section><h4>Order information</h4><dl className="ph-reference-grid">{Object.entries(row.order_details).filter(([, value]) => value !== null).map(([key, value]) => <div key={key}><dt>{readablePayment(key)}</dt><dd>{String(value)}</dd></div>)}</dl></section>}
        {!!(row.bookings.length || row.membership_ids.length || row.wallet_entries.length) && <section><h4>Linked purchases</h4><div className="ph-linked-list">
          {row.bookings.map(b => <Link key={b.id} to={`/bookings/${b.id}`} className="ph-linked"><Icon name="ticket" size={18} /><span><strong>Booking #{b.id}</strong><small>{[b.date ? dateLabel(b.date) : null, b.status ? readablePayment(b.status) : null, b.quantity ? `${b.quantity} ${b.quantity === 1 ? 'visitor' : 'visitors'}` : null].filter(Boolean).join(' · ')}</small></span>{b.amount && <span>{money(b.amount, b.currency || row.currency)}</span>}<Icon name="chevron" size={16} /></Link>)}
          {row.membership_ids.map(id => <Link key={id} to={`/membership/${id}`} className="ph-linked"><Icon name="gym" size={18} /><span><strong>Membership #{id}</strong><small>View membership details</small></span><Icon name="chevron" size={16} /></Link>)}
          {row.wallet_entries.map(w => <div key={w.id} className="ph-linked"><Icon name="wallet" size={18} /><span><strong>Wallet entry #{w.id}</strong><small>{w.direction} · {readablePayment(w.type)}</small></span><span>{money(w.amount, row.currency)}</span></div>)}
        </div></section>}
        <section><div className="ph-attempt-heading"><h4>Payment attempts</h4><span>{row.attempts.length} recorded</span></div>
          {row.attempts.length ? <ol className="ph-attempts">{row.attempts.map((a, index) => <li key={a.transaction_id}><div className="ph-attempt-top"><span>Attempt {index + 1}</span><PaymentBadge status={a.status} /><strong>{money(a.amount, a.currency || row.currency)}</strong></div><dl className="ph-reference-grid"><div><dt>Transaction</dt><dd>{a.transaction_id}</dd></div><div><dt>Refunded amount</dt><dd>{money(a.refunded_amount, a.currency || row.currency)}</dd></div><div><dt>First observed</dt><dd>{istDateTime(a.first_seen_at)}</dd></div><div><dt>Last checked</dt><dd>{istDateTime(a.updated_at)}</dd></div></dl></li>)}</ol>
            : <p className="ph-empty-attempts">No attempt details recorded. Check the original payment status to reconcile available attempts.</p>}
          <p className="ph-fine-print">Attempt history includes previously reconciled records only. First observed is not the provider’s payment time.</p>
        </section>
      </div>
    </details>
    <footer className="ph-card-footer"><span><Icon name="shield" size={14} />{row.checkout_id ? 'Gateway checkout record' : 'Legacy gateway record'}</span>{row.checkout_id && <Button variant="text" disabled={pending} onClick={onManage}>{historyAction(row.status)}<Icon name="arrow" size={16} /></Button>}</footer>
  </article>
}

export default function PaymentHistory() {
  const [page, setPage] = useState(0), [status, setStatus] = useState(''), [kind, setKind] = useState('')
  const [checkout, setCheckout] = useState<PaymentCheckout | null>(null)
  const [opening, setOpening] = useState(false)
  const [dialogError, setDialogError] = useState('')
  const dialogId = useRef<string | null>(null)
  const mutation = useMutation()
  const data = useResource(() => request<{ items: PaymentRow[]; total: number }>(`/payments/history?${new URLSearchParams({ limit: '20', offset: String(page * 20), ...(status ? { status } : {}), ...(kind ? { kind } : {}) })}`, { cache: 'no-store' }), `payment-history:${page}:${kind}:${status}`)
  const resetFilters = () => { setStatus(''); setKind(''); setPage(0) }
  const closeDialog = () => { dialogId.current = null; setOpening(false); setCheckout(null); setDialogError(''); data.retry() }
  const manage = (row: PaymentRow) => void mutation.run(async () => {
    const id = row.checkout_id!
    dialogId.current = id; setCheckout(null); setDialogError(''); setOpening(true)
    try {
      const next = await paymentService.refresh(id)
      if (dialogId.current === id) setCheckout(next)
      data.retry()
    } catch (error) {
      if (dialogId.current === id) setDialogError(error instanceof Error ? error.message : 'Unable to check payment status. Please try again.')
    } finally { if (dialogId.current === id) setOpening(false) }
  })
  const total = data.data?.total ?? 0
  const filtered = !!(kind || status)
  return <div className="ph-page">
    <Link to="/profile" className="ph-back"><Icon name="back" size={16} />Back to account</Link>
    <header className="ph-header"><div><span className="ph-eyebrow">YOUR FITIGO ACCOUNT</span><h1>Payment history</h1><p>Your workouts, memberships and recharges. All in one place.</p></div><Link to="/profile/history" className="fg-button fg-button--secondary"><Icon name="clock" size={17} />Check-in history</Link></header>
    <div className="ph-scope"><span className="ph-scope-icon"><Icon name="shield" size={22} /></span><div><strong>Clear records. Every step of the way.</strong><p>Razorpay and Cashfree purchases, including gateway wallet recharges. Test and live payments are labelled separately.</p></div><Link to="/wallet" className="fg-inline-link">Wallet ledger<Icon name="arrow" size={16} /></Link></div>
    <section className="ph-filter-panel" aria-label="Payment history filters"><div className="ph-filter-heading"><span><Icon name="filter" size={17} />Filter payments</span>{filtered && <Button variant="text" onClick={resetFilters}>Clear filters</Button>}</div><div className="ph-filters">
      <label className="fg-field">Purchase type<select value={kind} onChange={e => { setKind(e.target.value); setPage(0) }}><option value="">All purchases</option>{purchaseTypes.map(type => <option key={type.value} value={type.value}>{type.label}</option>)}</select></label>
      <label className="fg-field">Payment status<select value={status} onChange={e => { setStatus(e.target.value); setPage(0) }}><option value="">All statuses</option>{historyStatuses.map(value => <option key={value} value={value}>{historyStatus(value).label}</option>)}</select></label>
      <Button className="ph-reload" variant="secondary" disabled={data.loading || mutation.pending} onClick={data.retry}><Icon name="clock" size={16} />Refresh list</Button>
    </div></section>
    <div className="ph-list-heading"><h2>{filtered ? 'Matching payments' : 'Your transactions'}{!data.loading && !data.error && <span className="ph-count">{total}</span>}</h2><span>Newest first · Times in IST</span></div>
    <section className="ph-list" aria-label="Payment records" aria-busy={data.loading}>
      {data.loading ? <Skeleton cards={3} /> : data.error ? <ErrorState message={data.error} retry={data.retry} /> : data.data?.items.length ? data.data.items.map(row => <PaymentCard key={row.id} row={row} pending={mutation.pending} onManage={() => manage(row)} />)
        : <EmptyState title={filtered ? 'No matching payments' : page ? 'No payments on this page' : 'Your payment history starts here'} description={filtered ? 'Try a different purchase type or payment status.' : 'Your gateway purchases will appear here when you make a booking, buy a membership or recharge your wallet.'} action={filtered ? <Button variant="secondary" onClick={resetFilters}>Clear filters</Button> : page ? <Button variant="secondary" onClick={() => setPage(0)}>Back to first page</Button> : <Link to="/explore" className="fg-button fg-button--primary">Explore gyms<Icon name="arrow" size={16} /></Link>} />}
    </section>
    {!data.loading && !data.error && (total > 0 || page > 0) && <nav className="ph-pagination" aria-label="Payment history pages"><p>{data.data?.items.length ? `Showing ${page * 20 + 1}–${page * 20 + data.data.items.length} of ${total}` : 'No records on this page'}<small>Page {page + 1}{total > 0 ? ` of ${Math.max(page + 1, Math.ceil(total / 20))}` : ''}</small></p><div><Button variant="secondary" disabled={!page} onClick={() => setPage(value => value - 1)}><Icon name="back" size={15} />Previous</Button><Button variant="secondary" disabled={!data.data || (page + 1) * 20 >= total} onClick={() => setPage(value => value + 1)}>Next<Icon name="arrow" size={15} /></Button></div></nav>}
    <div className="ph-footer-note"><Icon name="help" size={18} /><p>Included membership visits are access records, not additional charges. Wallet spending and MVP credits appear only in the <Link to="/wallet" className="fg-inline-link">Wallet ledger</Link>. Amounts on these cards describe each purchase, not a combined live-money total.</p></div>
    {(opening || checkout || dialogError) && <Modal title="Payment status & actions" onClose={closeDialog} className="ph-manage-dialog">
      {opening ? <p role="status" className="ph-dialog-loading">Checking the original payment with the provider…</p> : dialogError ? <Alert>{dialogError}</Alert> : checkout && <><div className="ph-dialog-summary"><span>{purchasePresentation(checkout.kind).label}</span><strong>{money(checkout.amount, checkout.currency)}</strong></div><p className="ph-fine-print">{checkout.provider} · {checkout.mode === 'test' ? 'Test mode — no real money' : 'Live mode'}</p><GatewayPayment key={checkout.id} initial={checkout} presentation="checkout" onPaid={data.retry} /></>}
    </Modal>}
  </div>
}