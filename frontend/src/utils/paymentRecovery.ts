import type { PaymentCheckout } from '../services/paymentService'

export function paymentRecoverySummary(checkout: PaymentCheckout) {
  const held = checkout.wallet_status === 'HELD'
  if (checkout.can_resume_reserved_membership) return { title: 'Original payment can be resumed', message: 'Your wallet funds are still reserved. Resume the original membership with the same order and payment split. This does not start payment for a different plan or release the reservation.' }
  switch (checkout.recovery_status) {
    case 'PAID': return { title: 'Payment confirmed', message: 'FitiGo has verified this payment.' }
    case 'REFUNDED': return { title: 'Payment refunded', message: 'Review the payment history for this purchase.' }
    case 'SAFELY_CLOSED': return { title: 'Checkout safely closed', message: 'Review the selected plan, current price and available wallet balance before starting a new payment.' }
    case 'REVIEW_REQUIRED': return { title: 'Payment needs review', message: `Payment evidence requires review. Do not pay again.${held ? ' Wallet funds remain reserved.' : ''} Contact support with the details below.` }
    case 'PROCESSING': return { title: 'Confirming your payment', message: `The original payment is still processing. Do not pay again.${held ? ' Wallet funds remain reserved.' : ''}` }
    case 'CANCELLATION_PENDING': return { title: 'Cancellation pending', message: `Cancellation is being checked with the payment provider. Do not pay again.${held ? ' Wallet funds stay reserved until safe closure is confirmed.' : ''}` }
    case 'RESUMABLE': return { title: checkout.status === 'FAILED' ? 'Payment attempt failed' : 'Awaiting payment', message: 'You can resume this original purchase with its existing payment amount and funding split.' }
    default: return { title: 'Payment resolution required', message: `${checkout.payment_blocked_reason === 'WALLET_HOLD_RECONCILING' ? 'The wallet reservation deadline passed, but this does not close the payment. ' : ''}The original payment is unresolved.${held ? ' Wallet funds remain reserved, not charged.' : ''} Refresh its status or contact support; do not start another payment.` }
  }
}

export function paymentSupportDraft(checkout: PaymentCheckout) {
  const summary = paymentRecoverySummary(checkout)
  // Explicit allowlist: never serialize checkout/session/signature/key objects.
  return {
    category: 'TECHNICAL', subject: 'Unresolved membership payment',
    body: [
      `Original checkout reference: ${checkout.id}`,
      `Order reference: ${checkout.order_reference || 'Not available'}`,
      `Provider order reference: ${checkout.gateway_order_id || 'Not available'}`,
      `Payment reference: ${checkout.payment_reference || 'Not available'}`,
      `Purchase amount: ${checkout.currency} ${checkout.total_amount ?? checkout.amount}`,
      `Wallet reservation amount: ${checkout.currency} ${checkout.wallet_amount || '0.00'} (${checkout.wallet_status || 'NONE'})`,
      `Gateway-funded amount: ${checkout.currency} ${checkout.gateway_amount ?? checkout.amount}`,
      `Current recovery status: ${checkout.recovery_status || 'RESOLUTION_REQUIRED'} — ${summary.title}`,
      `Checkout status: ${checkout.status}; reason: ${checkout.payment_blocked_reason || 'None'}`,
      `Environment: ${checkout.mode}`,
      'Please investigate the original payment. This request does not authorize a wallet release or a new payment.',
    ].join('\n'),
  }
}