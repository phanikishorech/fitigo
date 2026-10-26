import type { PaymentCheckout } from '../services/paymentService'

type CashfreeResult = { error?: unknown; redirect?: boolean; paymentDetails?: unknown }
declare global { interface Window { Cashfree?: (options: { mode: 'sandbox' | 'production' }) => { checkout: (options: { paymentSessionId: string; redirectTarget: '_modal' }) => Promise<CashfreeResult> } } }
let loading: Promise<void> | undefined

export function loadCashfree(): Promise<void> {
  if (window.Cashfree) return Promise.resolve()
  if (loading) return loading
  loading = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    const fail = () => { clearTimeout(timer); script.remove(); loading = undefined; reject(new Error('Unable to load secure checkout. Refresh payment status before retrying.')) }
    const timer = window.setTimeout(fail, 20000)
    script.src = 'https://sdk.cashfree.com/js/v3/cashfree.js'; script.async = true
    script.onload = () => { clearTimeout(timer); if (window.Cashfree) resolve(); else fail() }
    script.onerror = fail
    document.head.appendChild(script)
  })
  return loading
}

export async function openCashfree(checkout: PaymentCheckout): Promise<{ type: 'returned' | 'cancelled' }> {
  if (!checkout.can_pay || checkout.provider !== 'CASHFREE' || !checkout.payment_session_id ||
      !['sandbox', 'production'].includes(checkout.environment) ||
      checkout.environment !== (checkout.mode === 'test' ? 'sandbox' : 'production')) {
    throw new Error('Checkout is not available. Refresh payment status.')
  }
  await loadCashfree()
  const result = await window.Cashfree!({ mode: checkout.environment }).checkout({ paymentSessionId: checkout.payment_session_id, redirectTarget: '_modal' })
  // SDK completion (including paymentDetails) says nothing about paid status.
  // Cashfree combines dismissal and payment errors in result.error.
  return { type: result?.error ? 'cancelled' : 'returned' }
}