import { ApiError, request } from './client'

export type PlatformPlan = {
  id: number; code: string; name: string; membership_type: 'MULTI_GYM'; description: string | null
  duration_value: number; duration_unit: 'DAY' | 'MONTH' | 'YEAR'
  base_price: string; final_price: string; discount_amount: string; discount_percentage: string | null; currency: string
  offer: { id: number; kind: 'FIXED' | 'PERCENTAGE'; title: string | null; valid_until: string } | null
  benefits: string[]; badge: string | null; display_order: number; is_active: boolean; version: number
  access_rule: { scope: 'ELIGIBLE_PARTNER_GYMS'; daily_access: number }; pause_rule: { allowed: boolean; max_pause_days: number } | null; purchase_available: boolean
}
export type PlatformCatalog = { items: PlatformPlan[]; server_time: string; checkout_available: boolean; checkout_unavailable_reason: string | null; payment_mode: string }
export type PlatformOrder = {
  id: string; status: string; payment_status: string; eligibility_status: string
  plan: PlatformPlan; current_plan: PlatformPlan | null; requires_review: boolean; created_at: string
  payment_available: boolean; membership_id: number | null; quote_token: string | null; payment_mode: string
  wallet_balance: string | null; wallet_currency: string | null; wallet_transaction_id: number | null
}

export const platformMembershipService = {
  catalog: () => request<PlatformCatalog>('/memberships/plans?membership_type=MULTI_GYM', { cache: 'no-store' }),
  detail: (id: number) => request<PlatformPlan>(`/memberships/plans/${id}`, { cache: 'no-store' }),
  createOrder: (planId: number, key: string) => request<PlatformOrder>('/memberships/orders', {
    method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify({ plan_id: planId }), cache: 'no-store',
  }),
  order: (id: string) => request<PlatformOrder>(`/memberships/orders/${encodeURIComponent(id)}`, { cache: 'no-store' }),
  payWallet: (id: string, quote: string) => request<PlatformOrder>(`/memberships/orders/${encodeURIComponent(id)}/pay-wallet`, { method: 'POST', body: JSON.stringify({ accepted_quote: quote }) }),
}

export function planLoadError(error: unknown) {
  if (error instanceof ApiError && [0, 401, 403, 429].includes(error.status)) return error.message
  return 'Unable to load membership plans.'
}

export function planDuration(plan: Pick<PlatformPlan, 'duration_value' | 'duration_unit'>) {
  const unit = { DAY: 'day', MONTH: 'month', YEAR: 'year' }[plan.duration_unit]
  return `${plan.duration_value} ${unit}${plan.duration_value === 1 ? '' : 's'}`
}