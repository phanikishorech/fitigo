import { request } from '../services/client'
import type { Share } from './agreementService'

export type PercentageSettings = { revenue: Share; gateway_fee: Share }
export type GymFinancialSettings = {
  contract_version: 1
  individual: PercentageSettings; single_gym: PercentageSettings; no_show: PercentageSettings
  multi_gym: { method: 'MONTHLY_VERIFIED_VISIT_VOLUME'; reference_amount: string; reference_visits: number; gateway_fee: Share; period_timezone: 'Asia/Kolkata' | null; rounding: 'MONTHLY_TOTAL_HALF_UP' | null; version_boundary: 'PIN_AT_ADMISSION' | null; purchase_fee_attribution: 'MEMBERSHIP_COMPLETE_EQUAL_VISITS' | null; invalidated_visit_correction: 'APPEND_ONLY_SOURCE_BACKED' | null; fitigo_earnings: 'NOT_APPROVED' }
  settlements: { booking_cycle: 'WEEKLY' | 'MONTHLY' | null; multi_gym_cycle: 'MONTHLY' | null; minimum_payout: string | null; admin_approval_required: true; automatic_transfers: false
    single_gym_cycle?: 'UPFRONT' | 'WEEKLY' | 'MONTHLY' | null; cutoff_time?: string | null; timezone?: 'Asia/Kolkata' | 'UTC' | null
    weekly_cutoff_day?: number | null; monthly_cutoff_day?: number | null; short_month?: 'LAST_CALENDAR_DAY' | 'NEXT_MONTH' | null; holding_days?: number | null
    eligible_deductions?: ('ACTUAL_TAX_WITHHOLDING' | 'APPROVED_SOURCE_ADJUSTMENT')[] | null; payout_eligibility?: 'VERIFIED_NET_SOURCE_UNDISPUTED' | null
    partial_settlement?: 'ALLOW_WITH_ALLOCATION_LINKS' | 'FULL_ENTITLEMENT_ONLY' | null; failed_settlement?: 'REMAIN_OUTSTANDING_REQUIRE_EVIDENCE' | null }
  single_gym_entitlement: 'UPFRONT_ON_VERIFIED_PURCHASE'; no_show_eligibility: 'EXPLICIT_AUTHORIZATION_ONLY'
  gateway_fee_basis: 'ACTUAL_PROVIDER_EVIDENCE_ONLY'; unknown_fee: 'GROSS_RECORDED_NET_PENDING'; wallet_gateway_fee: 'NONE'
}
export type SettingsVersion = { id: number; version: number; state: string; effective_from: string; applies_until: string | null; actor_id: number; created_at: string; reason: string; terms: Record<string, unknown> | null }
export type GymSettingsConfig = { gym_id: number; gym_name: string; mode: 'test' | 'live'; available: boolean; reason?: string; posting_enabled: false; processing_blockers: string[]; template: GymFinancialSettings | null; latest_version: number; latest: SettingsVersion | null; effective: SettingsVersion | null; legacy_replacement_required: boolean; history: SettingsVersion[]; total: number }
export type SettingsInput = { mode: 'test' | 'live'; gym_id: number; expected_version: number; expected_effective_version_id: number | null; effective_from: string; settings: GymFinancialSettings; reason: string; acknowledge_configuration_only: boolean; acknowledge_legacy_replacement: boolean }
export const gymFinancialSettingsService = {
  gyms: (query: string, page = 0) => request<{ items: { id: number; name: string }[]; total: number }>(`/admin/financial-settings/gyms?${new URLSearchParams({ q: query, limit: '20', offset: String(page * 20) })}`, { cache: 'no-store' }),
  get: (mode: 'test' | 'live', gymId: number, page = 0) => request<GymSettingsConfig>(`/admin/financial-settings?${new URLSearchParams({ mode, gym_id: String(gymId), limit: '20', offset: String(page * 20) })}`, { cache: 'no-store' }),
  create: (payload: SettingsInput, key: string) => request<SettingsVersion>('/admin/financial-settings', { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(payload), cache: 'no-store' })
}