import type { IconName } from '../components/common/Icon'

export const purchaseTypes: { value: string; label: string; icon: IconName }[] = [
  { value: 'CART', label: 'Gym visits', icon: 'bag' },
  { value: 'BOOKING', label: 'Gym booking', icon: 'ticket' },
  { value: 'SINGLE_GYM', label: 'Single-gym membership', icon: 'gym' },
  { value: 'MULTI_GYM', label: 'Multi-gym membership', icon: 'spark' },
  { value: 'WALLET_TOPUP', label: 'Wallet recharge', icon: 'wallet' }
]
export const historyStatuses = ['CREATED', 'CREATING', 'PENDING', 'PAID', 'FAILED', 'CANCELLED', 'REFUNDED', 'REVIEW_REQUIRED', 'PARTIALLY_REFUNDED', 'SUPERSEDED']
export function readablePayment(value: string): string {
  return value.replaceAll('_', ' ').toLowerCase().replace(/^\w/, char => char.toUpperCase())
}
export function purchasePresentation(kind: string) {
  return purchaseTypes.find(type => type.value === kind) ?? { value: kind, label: readablePayment(kind), icon: 'bag' as const }
}
export function historyStatus(status: string): { label: string; tone: 'success' | 'warning' | 'danger' | 'neutral'; icon: IconName } {
  if (status === 'PAID' || status === 'SUCCESS') return { label: status === 'PAID' ? 'Paid' : 'Successful', tone: 'success', icon: 'check' }
  if (status === 'FAILED') return { label: 'Failed', tone: 'danger', icon: 'close' }
  if (status === 'REVIEW_REQUIRED') return { label: 'Needs review', tone: 'warning', icon: 'help' }
  if (['CREATED', 'CREATING', 'PENDING', 'INITIATED'].includes(status)) return { label: status === 'CREATING' ? 'Processing' : status === 'CREATED' ? 'Created' : 'Pending', tone: 'warning', icon: 'clock' }
  if (status === 'SUPERSEDED') return { label: 'Replaced', tone: 'neutral', icon: 'arrow' }
  if (status === 'REFUNDED' || status === 'PARTIALLY_REFUNDED') return { label: status === 'REFUNDED' ? 'Refunded' : 'Partially refunded', tone: 'neutral', icon: 'back' }
  return { label: readablePayment(status), tone: 'neutral', icon: 'clock' }
}
export function paymentHistoryNotice(status: string, failureCode: string | null): string | null {
  if (failureCode === 'PAYMENT_AMOUNT_MISMATCH') return 'The provider reports a different paid amount. No access or wallet credit was granted. Do not pay this order again; contact support with the payment reference.'
  if (status === 'REVIEW_REQUIRED' && failureCode === 'FULFILLMENT_UNAVAILABLE') return 'Payment received, but the purchase could not be confirmed. Do not pay again. Contact support with the payment reference.'
  if (status === 'REVIEW_REQUIRED') return 'This payment needs review. Do not pay again. Check its status or contact support with the payment reference.'
  if (status === 'SUPERSEDED') return 'Replaced in FitiGo, not cancelled at the gateway. Do not pay the old order. Any delayed payment will need review.'
  return null
}
export function historyAction(status: string): string {
  return ['CREATED', 'CREATING', 'PENDING', 'FAILED'].includes(status) ? 'Manage payment' : 'Check payment status'
}