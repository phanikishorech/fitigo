import { request } from '../services/client'
import { financialQuery, type FinancialReport } from './financialService'
import type { DateRange } from '../utils/dateRange'

export type BusinessFilters = DateRange & { gym_id?: number; mode?: 'test' | 'live' }
type CollectionCategory = 'individual' | 'single_gym' | 'multi_gym'
type SharingAvailability = { status: 'RECORDED_SUBTOTAL' | 'UNAVAILABLE'; reason: string | null; missing_tables: string[] }
export type BusinessSeries = { date: string; individual: number; single_gym: number; multi_gym: number; individual_collections: string; single_gym_collections: string; multi_gym_collections: string }
export type BusinessSummary = Pick<FinancialReport, 'date_from' | 'date_to' | 'mode' | 'options' | 'wallet' | 'bookings' | 'memberships' | 'customers' | 'gyms' | 'definitions'> & {
  overall: { visits: number; bookings: number; users: number; gyms: number; active_memberships: number }
  visits: { individual: number; single_gym: number; multi_gym: number; completed: number; upcoming: number; no_shows: number; cancelled: number }
  collections: { categories: Record<'individual' | 'single_gym' | 'multi_gym', string | null>; total: string | null; known_dated_total: string; known_dated_categories?: Record<'individual' | 'single_gym' | 'multi_gym', string>; category_complete?: Record<CollectionCategory, boolean>; excluded_by_category?: Record<CollectionCategory, number>; sharing_availability?: Record<'gym_gross_share' | 'fitigo_commission', SharingAvailability>; exclusions?: { checkout_id: string; category: string; reason: string }[]; exclusion_reasons?: Record<string, number>; undated_purchases: number; unattributed_purchases: number; gym_gross_share: string | null; fitigo_commission: string | null; complete: boolean }
  series: BusinessSeries[]
}
export function collectionCard(collections: BusinessSummary['collections'], key: CollectionCategory) {
  const complete = collections.category_complete?.[key] ?? collections.complete
  const known = collections.known_dated_categories?.[key]
  const partial = !complete && known != null && Number(known) > 0
  return { value: complete ? collections.categories[key] : partial ? known : null, partial, excluded: collections.excluded_by_category?.[key] ?? 0 }
}
export type MembershipPurchase = { id: number; customer_id: number; customer_name: string; email: string; gym_id: number | null; gym_name: string | null; kind: string; status: string; payment_status: string; purchased_at: string; valid_from: string; valid_until: string; purchase_amount: string; mode: string | null }
export type CustomerActivity = { wallet_balance: string | null; wallet_mode: string | null; memberships: { items: MembershipPurchase[]; total: number }; bookings: { id: number; date: string; status: string; gym_id: number; amount: string }[] }
export const businessService = {
  summary: (filters: BusinessFilters) => request<BusinessSummary>(`/admin/business/summary?${financialQuery(filters)}`, { cache: 'no-store' }),
  memberships: (filters: Record<string, string | number | undefined>) => request<{ total: number; items: MembershipPurchase[] }>(`/admin/business/memberships?${financialQuery(filters)}`, { cache: 'no-store' }),
  customer: (id: number) => request<CustomerActivity>(`/admin/business/customers/${id}`, { cache: 'no-store' }),
  attendance: (id: number) => request<{ completed_visitors: number; purchased_visitors: number; no_show: boolean; marked_at: string | null }>(`/admin/business/bookings/${id}/attendance`, { cache: 'no-store' })
}