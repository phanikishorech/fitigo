import { request } from '../services/client'
import type { DateRange } from '../utils/dateRange'
import type { OwnerDashboardSummary } from '../screens/GymOwner/api'

export type Scope = DateRange & { gym_id?: number }
export type SeriesPoint = { date: string; date_to: string; visits: number; revenue: string }
export type Analytics = { summary: OwnerDashboardSummary; grouping: 'daily' | 'weekly'; series: SeriesPoint[]; revenue_by_gym: { gym_id: number; gym_name: string; total: string; single_gym_membership: string; individual_booking: string }[] }
export type BookingRecord = { id: number; gym_name: string; date: string; start_time: string; slot_name: string; customer: string; visitors: string[]; access_source: string; quantity: number; amount: string; currency: string; status: string; attendance_status: string | null; category: string; payment_status: string | null }
export type Transaction = { id: string; record_id: number; category: string; gym_name: string; recorded_at: string; amount: string; recognized_amount: string; included: boolean; exclusion_reason?: string | null; currency: string; provider: string; mode: string | null; payment_status: string; checkout_status: string | null; booking_id: number | null; transaction_id: string | null }
export type Attendance = { id: number; gym_name: string; customer: string; category: string; recorded_at: string; booking_id: number | null }
export type Page<T> = { items: T[]; total: number }
function get<T>(path: string, params: Record<string, string | number | undefined>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== '') query.set(key, String(value)) })
  return request<T>(`/gym-owner/analytics${path}?${query}`, { cache: 'no-store' })
}
export const analyticsService = {
  overview: (scope: Scope) => get<Analytics>('', scope),
  bookings: (scope: Scope, page: number, category: string) => get<Page<BookingRecord>>('/bookings', { ...scope, category, limit: 10, offset: page * 10 }),
  transactions: (scope: Scope, page: number, category: string, payment_status: string) => get<Page<Transaction>>('/transactions', { ...scope, category, payment_status, limit: 10, offset: page * 10 }),
  attendance: (scope: Scope, page: number) => get<Page<Attendance>>('/attendance', { ...scope, limit: 10, offset: page * 10 })
}