import type { PaymentCheckout } from '../services/paymentService'
import { openRazorpay } from './razorpay'
import { openCashfree } from './cashfree'

export function openPayment(checkout: PaymentCheckout) {
  if (checkout.provider === 'CASHFREE') return openCashfree(checkout)
  // Missing provider is accepted only for old Razorpay API responses.
  if (!checkout.provider || checkout.provider === 'RAZORPAY') return openRazorpay(checkout)
  throw new Error('Unsupported payment provider. Refresh payment status.')
}