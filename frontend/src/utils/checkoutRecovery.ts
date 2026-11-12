import type { PaymentCheckout } from '../services/paymentService'

export function checkoutMessage(checkout: PaymentCheckout): string {
  const reason = checkout.payment_blocked_reason
  if (checkout.status === 'SUPERSEDED') return 'This checkout was replaced and cannot be reopened in FitiGo. The gateway order was not cancelled. Any delayed payment will be recorded for review; do not pay this old order.'
  if (reason === 'BOOKING_EXPIRED') return 'Booking payment window expired. This does not mean the payment failed. Refresh the original payment status before making another purchase.'
  if (reason === 'BOOKING_UNAVAILABLE') return 'This visit is no longer available for payment. Resolve the original checkout, then choose a future available visit.'
  if (reason === 'PAYMENT_PROCESSING') return 'Payment is processing. Do not pay again. Refresh payment status or contact support if it does not resolve.'
  if (reason === 'ORDER_UNRESOLVED') return 'The original gateway order is unresolved. A local cancellation does not prove that payment stopped. Refresh status or contact support; do not pay again.'
  if (reason === 'GATEWAY_UNAVAILABLE' || reason === 'SESSION_UNAVAILABLE') return 'This gateway checkout cannot be opened. Refresh payment status to check whether the original order can be safely closed.'
  if (checkout.status === 'PAID') return 'Payment confirmed by FitiGo.'
  if (checkout.status === 'REVIEW_REQUIRED' && checkout.failure_code === 'FULFILLMENT_UNAVAILABLE') return 'Payment received, but the booking could not be confirmed. Do not pay again. Contact support with the checkout reference in Payment details.'
  if (checkout.status === 'REVIEW_REQUIRED') return checkout.failure_code === 'PAYMENT_AMOUNT_MISMATCH'
    ? 'The gateway reports a different paid amount. No access or wallet credit was granted. Do not pay this order again. Contact support with this checkout ID.'
    : 'Payment requires review. Do not pay again. Contact support with this checkout ID.'
  if (checkout.status === 'CANCELLED') return 'Checkout closed. Review visit times, availability and prices before starting a new purchase.'
  if (checkout.status === 'FAILED' && checkout.can_pay) return 'Payment failed. You can retry this same checkout without creating another purchase.'
  if (['PENDING', 'CREATING', 'CREATED'].includes(checkout.status)) return 'Payment is not confirmed yet. Refresh status before retrying. Access or wallet credit has not been granted.'
  return `Payment status: ${checkout.status.toLowerCase().replaceAll('_', ' ')}.`
}

export function pendingCartCheckout(payments: PaymentCheckout[]): PaymentCheckout | undefined {
  return payments.find(p => p.kind === 'CART' && !['PAID', 'REFUNDED', 'REVIEW_REQUIRED', 'CANCELLED', 'SUPERSEDED'].includes(p.status))
    ?? payments.find(p => p.kind === 'CART' && p.status === 'CANCELLED' && !p.replacement_safe)
}