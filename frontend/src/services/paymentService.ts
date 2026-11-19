import { post, request } from './client'
import { cartMutation } from './customerActivity'

export type PaymentCheckout = {
  total_amount?: string; wallet_amount?: string; gateway_amount?: string; wallet_status?: string; wallet_transaction_id?: number | null; wallet_hold_expires_at?: string | null
  provider: 'RAZORPAY' | 'CASHFREE'; environment: 'sandbox' | 'production'; gateway_order_id: string | null; payment_session_id?: string | null
  id: string; kind: string; status: string; mode: 'test' | 'live'; amount: string; amount_minor: number; currency: string
  key_id: string; razorpay_order_id: string | null; booking_ids: number[]; membership_id: number | null; can_pay: boolean; failure_code: string | null
  payment_blocked_reason?: string | null; payment_expires_at?: string | null; can_cancel?: boolean; replacement_safe?: boolean
  can_request_cancel?: boolean; cancellation_requested?: boolean; plan_name?: string | null
  can_resume_reserved_membership?: boolean
  recovery_status?: 'PAID' | 'REVIEW_REQUIRED' | 'REFUNDED' | 'SAFELY_CLOSED' | 'PROCESSING' | 'CANCELLATION_PENDING' | 'RESUMABLE' | 'RESOLUTION_REQUIRED'
  can_contact_support?: boolean; order_reference?: string | null; payment_reference?: string | null
  cart_item_ids?: number[]
  items?: { booking_id: number; gym_name: string; booking_date: string; start_time: string | null; quantity: number; amount: string; currency: string }[]
}
export type PaymentSource = ({ kind: 'WALLET_TOPUP'; amount: string } | { kind: 'CART'; cart_item_ids?: number[]; confirm_razorpay_replacement?: boolean } | { kind: 'BOOKING'; booking_id: number } |
  { kind: 'SINGLE_GYM'; gym_id: number; plan_id: number; accepted_quote: string } |
  { kind: 'MULTI_GYM'; order_id: string; accepted_quote: string }) & { use_wallet?: boolean; wallet_amount?: string }
export type FundingQuote = { total_amount: string; wallet_amount: string; gateway_amount: string; wallet_balance: string; available_wallet_balance: string; reserved_balance: string; wallet_unavailable_reason: string | null; provider: string; currency: string; mode: string }
export type MembershipSource = Extract<PaymentSource, { kind: 'SINGLE_GYM' | 'MULTI_GYM' }>
export type MembershipRecovery = { checkout: PaymentCheckout | null; matches_selection: boolean }
export type GatewayCallback = { razorpay_payment_id: string; razorpay_order_id: string; razorpay_signature: string }
export const paymentService = {
  recoverMembership: (source: MembershipSource) => {
    const query = new URLSearchParams(source.kind === 'MULTI_GYM'
      ? { kind: source.kind, order_id: source.order_id }
      : { kind: source.kind, gym_id: String(source.gym_id), plan_id: String(source.plan_id) })
    return request<MembershipRecovery>(`/payments/membership-checkout?${query}`, { cache: 'no-store' })
  },
  quote: (source: PaymentSource) => post<FundingQuote>('/payments/quote', source),
   config: () => request<{ enabled: boolean; gateway_required: boolean; mode: 'test' | 'live'; provider: 'RAZORPAY' | 'CASHFREE' }>('/payments/config', { cache: 'no-store' }),
   create: (source: PaymentSource, key: string) => cartMutation(request<PaymentCheckout>('/payments/checkouts', {
    method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(source), cache: 'no-store'
   })),
  recent: () => request<PaymentCheckout[]>('/payments/checkouts', { cache: 'no-store' }),
  status: (id: string) => request<PaymentCheckout>(`/payments/checkouts/${id}`, { cache: 'no-store' }),
  refresh: (id: string) => cartMutation(post<PaymentCheckout>(`/payments/checkouts/${id}/refresh`)),
  resumeMembership: (id: string) => cartMutation(post<PaymentCheckout>(`/payments/checkouts/${id}/resume-membership`)),
  verify: (id: string, callback?: GatewayCallback) => cartMutation(post<PaymentCheckout>(`/payments/checkouts/${id}/verify`, callback || {})),
  cancel: (id: string) => cartMutation(post<PaymentCheckout>(`/payments/checkouts/${id}/cancel`))
}