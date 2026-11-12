import { request } from '../services/client'
import type { DateRange } from '../utils/dateRange'

export type Grain = 'day' | 'week' | 'month'
export type AnalyticsMetrics = {
  bookings: number; places: number; confirmed: number; pending: number; cancelled: number; expired: number
  attended: number; no_show: number; paid_bookings: number; paid_amount: string; failed_payments: number
  refunded_payments: number; review_required: number; confirmation_rate: number | null; cancellation_rate: number | null
}
export type GymOption = { id: number; name: string; country: string; state: string; city: string }
export type AnalyticsGym = GymOption & AnalyticsMetrics & { status: string; is_active: boolean; unique_customers: number }
export type AnalyticsLocation = AnalyticsMetrics & { country: string; state: string; city: string; gyms: number; active_gyms: number }
export type AnalyticsPeriod = AnalyticsMetrics & DateRange & { period: string }
export type AnalyticsFilters = DateRange & { grain: Grain; gym_id?: number; country?: string; state?: string; city?: string }
export type Analytics = DateRange & {
  grain: Grain; timezone: string; generated_at: string
  scope: { mode: 'test' | 'live'; currency: string; date_basis: string; basis: string }
  summary: AnalyticsMetrics & { unique_customers: number }
  previous: AnalyticsMetrics & DateRange & { unique_customers: number }
  catalog: { gyms: number; active_gyms: number; gyms_with_bookings: number }
  gyms: AnalyticsGym[]; locations: AnalyticsLocation[]; series: AnalyticsPeriod[]; options: GymOption[]
}
export function analyticsQuery(filters: AnalyticsFilters) {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => { if (value !== undefined) params.set(key, String(value)) })
  return params.toString()
}
export const analyticsService = {
  report: (filters: AnalyticsFilters, signal?: AbortSignal) => request<Analytics>(`/admin/analytics?${analyticsQuery(filters)}`, { signal, cache: 'no-store' })
}