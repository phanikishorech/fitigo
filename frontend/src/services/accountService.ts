import type { GymMembershipPlan, PurchaseMembershipResponse } from '../screens/GymDetails/api'
import type { WalletBalanceResponse } from '../screens/Checkout/api'
import { post, request } from './client'

export type Profile = { user_id: number; full_name: string; profile_image: string | null; member_since: string; membership_status: string | null; has_membership_history?: boolean }
export type User = { id: number; first_name: string | null; last_name: string | null; email: string; phone: string | null; is_email_verified?: boolean; is_phone_verified?: boolean }
export type MembershipSummary = { membership_id: number | null; plan_name: string | null; status: string | null; start_date: string | null; end_date: string | null; membership_scope: string | null; active_gyms: { gym_id: number; gym_name: string; locality?: string | null; city?: string | null }[]; membership_features: string[] }
export type Membership = Omit<PurchaseMembershipResponse, 'gym_id' | 'plan_id'> & { gym_id: number | null; plan_id: number | null; payment_provider: string; payment_status: string; membership_type?: 'SINGLE_GYM' | 'MULTI_GYM'; terms_snapshot?: { name: string; duration_value: number; duration_unit: string } | null; wallet_transaction_id?: number | null }
export type WalletTransaction = { id: number; direction: string; txn_type: string; amount: string; currency: string; description: string | null; created_at: string }
export type Wallet = WalletBalanceResponse & { transactions: WalletTransaction[] }
export type AccessDay = { date: string; status: string; qr_available: boolean; qr_status: string | null; gym_id?: number | null; gym_name: string | null; checkin_time: string | null }
export type AccessCalendar = { days: AccessDay[]; access_type: string | null; gym: { id: number; name: string } | null }
export type TodayAccess = { status: 'ACTIVE'; qr_token: string; expires_at: string; access_type: string; gym: { id: number; name: string } | null } | { status: 'USED'; gym_name: string | null; used_at: string } | { status: 'PAUSED' | 'EXPIRED' | 'NO_ACCESS' }
export const profileService = { get: () => request<Profile>('/profile'), me: () => request<User>('/users/me'),
  update: (body: { first_name: string; last_name: string; email: string; phone: string | null; current_password?: string }) => request<{ user: User; reauthenticate: boolean }>('/users/me', { method: 'PATCH', body: JSON.stringify(body) }) }
export const walletService = {
  balance: () => request<WalletBalanceResponse>('/wallet/balance'),
  transactions: () => request<Wallet>('/wallet/transactions?limit=100'),
  recharge: (_amount: number) => Promise.reject(new Error('Use secure gateway checkout from Recharge wallet. No credit has been added.'))
}
export const membershipService = {
  plans: (gymId: number) => request<GymMembershipPlan[]>(`/memberships/gyms/${gymId}/plans`),
  mine: () => request<Membership[]>('/memberships/me'),
  summary: () => request<MembershipSummary>('/profile/membership', { cache: 'no-store' }),
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
    const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', year: 'numeric', month: 'numeric' }).formatToParts(new Date())
    return accessService.calendar(Number(parts.find(p => p.type === 'year')!.value), Number(parts.find(p => p.type === 'month')!.value))
  }
}
export type CustomerReview = { id: number; rating: number; comment: string | null; status: string }
export type BookingReview = { booking_id: number; gym_id: number; gym_name: string; can_review: boolean; reason: string | null; review: CustomerReview | null }
export const reviewService = {
  eligibility: (bookingId: number) => request<BookingReview>(`/profile/bookings/${bookingId}/review`, { cache: 'no-store' }),
  submit: (gymId: number, rating: number, comment: string, bookingId: number) => post<CustomerReview>(`/gyms/${gymId}/reviews`, { rating, comment: comment.trim() || null, booking_id: bookingId })
}
