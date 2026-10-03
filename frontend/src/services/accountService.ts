import type { GymMembershipPlan, PurchaseMembershipResponse } from '../screens/GymDetails/api'
import type { WalletBalanceResponse, WalletTopupResponse } from '../screens/Checkout/api'
import { post, request } from './client'

export type Profile = { user_id: number; full_name: string; profile_image: string | null; member_since: string; membership_status: string | null }
export type User = { id: number; first_name: string | null; last_name: string | null; email: string; phone: string | null }
export type MembershipSummary = { membership_id: number | null; plan_name: string | null; status: string | null; start_date: string | null; end_date: string | null; membership_scope: string | null; active_gyms: { gym_id: number; gym_name: string; locality?: string | null; city?: string | null }[]; membership_features: string[] }
export type Membership = Omit<PurchaseMembershipResponse, 'gym_id' | 'plan_id'> & { gym_id: number | null; plan_id: number | null; payment_provider: string; payment_status: string; membership_type?: 'SINGLE_GYM' | 'MULTI_GYM'; terms_snapshot?: { name: string; duration_value: number; duration_unit: string } | null; wallet_transaction_id?: number | null }
export type WalletTransaction = { id: number; direction: string; txn_type: string; amount: string; currency: string; description: string | null; created_at: string }
export type Wallet = WalletBalanceResponse & { transactions: WalletTransaction[] }
export type AccessDay = { date: string; status: string; qr_available: boolean; qr_status: string | null; gym_id?: number | null; gym_name: string | null; checkin_time: string | null }
export type AccessCalendar = { days: AccessDay[]; access_type: string | null; gym: { id: number; name: string } | null }
export type TodayAccess = { status: 'ACTIVE'; qr_token: string; expires_at: string; access_type: string; gym: { id: number; name: string } | null } | { status: 'USED'; gym_name: string | null; used_at: string } | { status: 'PAUSED' | 'EXPIRED' | 'NO_ACCESS' }
export const profileService = { get: () => request<Profile>('/profile'), me: () => request<User>('/users/me') }
export const walletService = {
  balance: () => request<WalletBalanceResponse>('/wallet/balance'),
  transactions: () => request<Wallet>('/wallet/transactions?limit=100'),
  recharge: (amount: number) => {
    if (!import.meta.env.DEV) return Promise.reject(new Error('Online recharge is not available yet. No payment has been taken.'))
    return post<WalletTopupResponse>('/wallet/topup', { amount, currency: 'INR' })
  }
}
export const membershipService = {
  plans: (gymId: number) => request<GymMembershipPlan[]>(`/memberships/gyms/${gymId}/plans`),
  mine: () => request<Membership[]>('/memberships/me'),
  summary: () => request<MembershipSummary>('/profile/membership'),
  quote: (gymId: number, planId: number) => request<MembershipWalletQuote>(`/memberships/gyms/${gymId}/plans/${planId}/wallet-quote`, { cache: 'no-store' }),
  purchase: (gymId: number, planId: number, quote: string, key: string) => request<Membership>(`/memberships/gyms/${gymId}/purchase`, {
    method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify({ plan_id: planId, accepted_quote: quote }),
  })
}
export type MembershipWalletQuote = { plan: { name: string; final_price: string; currency: string; duration_value: number; duration_unit: string }; quote_token: string; payment_available: boolean; wallet_balance: string; wallet_currency: string; payment_mode: string }
export const accessService = {
  today: () => request<TodayAccess>('/customer/access/today', { cache: 'no-store' }),
  calendar: (year: number, month: number) => request<AccessCalendar>(`/customer/access-calendar?year=${year}&month=${month}`, { cache: 'no-store' }),
  // Read-only status checks must not mint QR credentials. The calendar exposes TODAY.
  current: () => {
    const now = new Date()
    return accessService.calendar(now.getUTCFullYear(), now.getUTCMonth() + 1)
  }
}
export const reviewService = { submit: (gymId: number, rating: number, comment: string) => post<{ id: number }>(`/gyms/${gymId}/reviews`, { rating, comment: comment.trim() || null }) }