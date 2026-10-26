import type { GatewayCallback, PaymentCheckout } from '../services/paymentService'

type CheckoutInstance = { open: () => void; close: () => void; on: (event: string, listener: () => void) => void }
declare global { interface Window { Razorpay?: new (options: Record<string, unknown>) => CheckoutInstance } }
let loading: Promise<void> | undefined
export function loadRazorpay(): Promise<void> {
  if (window.Razorpay) return Promise.resolve()
  if (loading) return loading
  loading = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    const fail = () => { clearTimeout(timer); script.remove(); loading = undefined; reject(new Error('Unable to load secure checkout. Retry or refresh payment status.')) }
    const timer = window.setTimeout(fail, 20000)
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'; script.async = true
    script.onload = () => { clearTimeout(timer); if (window.Razorpay) resolve(); else fail() }
    script.onerror = fail
    document.head.appendChild(script)
  })
  return loading
}

export async function openRazorpay(checkout: PaymentCheckout): Promise<{ type: 'success'; callback: GatewayCallback } | { type: 'cancelled' | 'failed' }> {
  if (!checkout.can_pay || !checkout.razorpay_order_id || !checkout.key_id.startsWith(`rzp_${checkout.mode}_`)) throw new Error('Checkout is not available. Refresh payment status.')
  await loadRazorpay()
  return new Promise(resolve => {
    let settled = false
    const finish = (result: { type: 'success'; callback: GatewayCallback } | { type: 'cancelled' | 'failed' }) => { if (!settled) { settled = true; resolve(result) } }
    const instance = new window.Razorpay!({
      key: checkout.key_id, order_id: checkout.razorpay_order_id, amount: checkout.amount_minor,
      currency: checkout.currency, name: 'FitiGo', description: checkout.mode === 'test' ? 'Test payment · no real money' : 'FitiGo purchase',
      handler: (callback: GatewayCallback) => finish({ type: 'success', callback }),
      modal: { ondismiss: () => finish({ type: 'cancelled' }) }, retry: { enabled: false }, theme: { color: '#15803d' }
    })
    instance.on('payment.failed', () => { finish({ type: 'failed' }); instance.close() })
    instance.open()
  })
}