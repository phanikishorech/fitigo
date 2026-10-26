import { post, request } from './client'

export type PaymentCheckout = {
  id: string; kind: string; status: string; mode: 'test' | 'live'; amount: string; amount_minor: number; currency: string
  key_id: string; razorpay_order_id: string | null; booking_ids: number[]; membership_id: number | null; can_pay: boolean; failure_code: string | null
}
export type PaymentSource = { kind: 'CART' } | { kind: 'BOOKING'; booking_id: number } |
  { kind: 'SINGLE_GYM'; gym_id: number; plan_id: number; accepted_quote: string } |
  { kind: 'MULTI_GYM'; order_id: string; accepted_quote: string }
export type GatewayCallback = { razorpay_payment_id: string; razorpay_order_id: string; razorpay_signature: string }
export const paymentService = {
  config: () => request<{ enabled: boolean; gateway_required: boolean; mode: 'test' | 'live' }>('/payments/config', { cache: 'no-store' }),
  create: (source: PaymentSource, key: string) => request<PaymentCheckout>('/payments/checkouts', {
    method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(source), cache: 'no-store'
  }),
  recent: () => request<PaymentCheckout[]>('/payments/checkouts', { cache: 'no-store' }),
  status: (id: string) => request<PaymentCheckout>(`/payments/checkouts/${id}`, { cache: 'no-store' }),
  refresh: (id: string) => post<PaymentCheckout>(`/payments/checkouts/${id}/refresh`),
  verify: (id: string, callback: GatewayCallback) => post<PaymentCheckout>(`/payments/checkouts/${id}/verify`, callback),
  cancel: (id: string) => post<PaymentCheckout>(`/payments/checkouts/${id}/cancel`)
}