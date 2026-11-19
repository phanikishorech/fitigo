import { request } from '../services/client'
import type { DateRange } from '../utils/dateRange'

export type FinancialFilters = DateRange & { gym_id?: number; mode?: 'test' | 'live'; source?: 'RAZORPAY' | 'CASHFREE' | 'WALLET' }
export type Unconfigured = { value: null; status: string; reason: string }
export type FinancialSeries = { date: string; attended_value: string; visits: number; membership_sales_value: string; no_show_gross: string; wallet_credits: string | null; wallet_spending: string | null }
export type FinancialReport = {
  version: number; date_from: string; date_to: string; mode: 'test' | 'live'; source: string | null; gym_id: number | null; currency: string; timezone: string; generated_at: string
  data_quality?: { unclassified_mode_bookings_excluded: number; capture_dates: string; refund_event_dates: string; historical_recognition_adjustments: string }
  options: { id: number; name: string }[]
  platform: { total_users: number; new_users: number; new_customers: number; active_gyms: number; pending_gyms: number; new_gyms: number; completed_visits: number; upcoming_bookings: number }
  revenue: { attended_booking_value: string; attended_wallet_funded_value: string; attended_booking_count: number; recognized_total: Unconfigured; fitigo_booking_income: Unconfigured; no_show_count: number; no_show_gross: string; no_show_fitigo_income: Unconfigured; no_show_owner_share: Unconfigured }
  bookings: { total: number; confirmed: number; cancelled: number; attended: number; no_show: number; pending: number; expired: number; upcoming: number; cancellation_rate: number | null; no_show_rate: number | null }
  memberships: { categories: Record<'SINGLE_GYM' | 'MULTI_GYM', { sales_count: number; sales_value: string; gateway_funded_value: string; wallet_funded_value: string; recognized_revenue: Unconfigured; active: number; expired: number; expiring_30_days: number }>; transfers: number; renewals: Unconfigured; plan_popularity: { membership_type: string; plan_id: number | null; platform_plan_id: number | null; sales: number; sales_value: string }[] }
  payments: { wallet_funded_purchase_value?: string | null; wallet_purchase_basis?: string; applicable: boolean; reason?: string; dated_collections: Unconfigured; undated: { provider: string; gross_collections: string; refunds_recorded: string; net_recorded: string; successful_payments: number; membership_collections: string; recharge_collections: string }[]; attempts: { total?: number; successful?: number; pending?: number; failed?: number; success_rate?: number | null; basis?: string }; gateway_fee: Unconfigured; mismatches: number; review_required?: number }
  wallet: { applicable: boolean; reason?: string; outstanding: string | null; stored_balance: string | null; credits: string | null; spending: string | null; ledger_net?: string; reconciliation_difference?: string; mismatched_accounts?: number; status?: string; unclassified_mode_balance?: string; debits?: string; booking_spending?: string; membership_spending?: string; unallocated_spending?: string; cancellation_credits?: string; opening_ledger_balance?: string; closing_ledger_balance?: string; movements_by_type?: { txn_type: string; direction: string; amount: string; count: number }[]; promotional_credits?: Unconfigured; adjustments?: Unconfigured; expirations?: Unconfigured; source_liability?: Unconfigured; liability_aging?: Unconfigured }
  settlements: Record<string, Unconfigured>
  customers: { active: number; repeat: number; previous_active: number | null; retained: number | null; retention_rate: number | null; visits_per_active: number | null; membership_conversion: Unconfigured; most_active: { user_id: number; visits: number }[] }
  gyms: { id: number; name: string; status: string; is_active: boolean; visits: number; attended_value: string; single_membership_sales_value: string; owner_payable: null; utilization: null }[]
  series: FinancialSeries[]; definitions: Record<string, string>
}
export type LedgerPage = { total: number; items: { id: number; account_id: number; direction: string; txn_type: string; amount: string; currency: string; checkout_id: string | null; reference: string | null; created_at: string }[] }
export function financialQuery(filters: Record<string, string | number | undefined>) {
  const query = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => { if (value !== undefined && value !== '') query.set(key, String(value)) })
  return query.toString()
}
export const financialService = {
  report: (view: 'dashboard' | 'analytics' | 'reports', filters: FinancialFilters) => request<FinancialReport>(`/admin/${view === 'dashboard' ? 'dashboard/summary' : view === 'analytics' ? 'analytics' : 'reports/financial'}?${financialQuery({ ...filters, financial: 'true' })}`, { cache: 'no-store' }),
  ledger: (filters: FinancialFilters, direction: string, txn_type: string, page: number) => request<LedgerPage>(`/admin/reports/wallet-ledger?${financialQuery({ date_from: filters.date_from, date_to: filters.date_to, mode: filters.mode, direction, txn_type, limit: 25, offset: page * 25 })}`, { cache: 'no-store' })
}