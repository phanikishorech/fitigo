import { request } from '../services/client'

export type Share = { gym_percent: string; fitigo_percent: string }
export type AgreementTerms = {
  policy_contract?: Record<string, unknown> | null
  marketplace_contract?: Record<string, unknown> | null
  visit_payout_contract?: Record<string, unknown> | null
  attended: Share; no_show: Share; single_gym: Share
  multi_gym: { payout_per_visit: string | null; visits_per_member_month: number | null; payout_cap_per_member_month: string | null }
  settlements: { booking_cycle: 'WEEKLY' | 'MONTHLY'; multi_gym_cycle: 'WEEKLY' | 'MONTHLY'; monthly_single_cycle: 'NEXT_CYCLE' | 'UPFRONT'; quarterly_single_cycle: 'NEXT_CYCLE' | 'UPFRONT'; half_yearly_single_cycle: 'NEXT_CYCLE' | 'UPFRONT'; yearly_single_cycle: 'NEXT_CYCLE' | 'UPFRONT'; minimum_payout: string; admin_approval_required: true }
  sharing_basis: 'AFTER_DISCOUNTS_EXCLUDING_TAX'; gateway_fees: 'SEPARATE_ACTUAL'; wallet_same_agreement: true
  group_basis: 'ATTENDED_VISITORS_WHEN_UNIT_PRICED'; business_model: 'AGENT_MARKETPLACE'; membership_recognition: 'NOT_APPROVED'
}
export type AgreementVersion = {
  policy_readiness?: PolicyReadiness
  id: number; scope_id: number; version: number; action: 'AGREEMENT' | 'INHERIT'; effective_from: string; effective_to: string | null; superseded_at: string | null; applies_until: string | null; state: string
  terms: AgreementTerms | null; agreement_reference: string; reason: string; ca_status: 'PENDING' | 'RECORDED_APPROVAL'; ca_reference: string | null; actor_id: number; created_at: string; statutory_reporting_enabled: false
}
export type AgreementConfig = {
  policy_catalog?: { schema: PolicySchema; empty: Record<string, unknown>; selection_instants: Record<string, string[]>; marketplace_schema?: PolicySchema; marketplace_empty?: Record<string, unknown>; visit_schema?: PolicySchema; visit_empty?: Record<string, unknown> }
  available: boolean; mode: 'test' | 'live'; gym_id: number | null; server_time: string; posting_enabled: false; statutory_reporting_enabled: false
  options: { id: number; name: string }[]; notice: string; reason?: string; limits_notice?: string
  latest_version: number; latest: AgreementVersion | null; effective: AgreementVersion | null; effective_scope?: 'GYM' | 'DEFAULT' | null; template: AgreementTerms | null; history: AgreementVersion[]; total: number
}
export type AgreementInput = {
  mode: 'test' | 'live'; gym_id: number | null; expected_version: number; effective_from: string; effective_to: string | null
  action: 'AGREEMENT' | 'INHERIT'; terms: AgreementTerms | null; agreement_reference: string; reason: string
  ca_status: 'PENDING' | 'RECORDED_APPROVAL'; ca_reference: string | null; acknowledge_configuration_only: boolean
}
export const agreementService = {
  validatePolicy: (terms: AgreementTerms) => request<PolicyReadiness>('/admin/financial-agreements/policy-validation', { method: 'POST', body: JSON.stringify(terms), cache: 'no-store' }),
  get: (mode: 'test' | 'live', gymId: number | null, page = 0) => request<AgreementConfig>(`/admin/financial-agreements?${new URLSearchParams({ mode, ...(gymId == null ? {} : { gym_id: String(gymId) }), limit: '20', offset: String(page * 20) })}`, { cache: 'no-store' }),
  create: (payload: AgreementInput, key: string) => request<AgreementVersion>('/admin/financial-agreements', { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(payload), cache: 'no-store' })
}
export type PolicySchema = { $ref?: string; $defs?: Record<string, PolicySchema>; title?: string; type?: string; const?: unknown; enum?: string[]; anyOf?: PolicySchema[]; properties?: Record<string, PolicySchema>; items?: PolicySchema; minimum?: number; maximum?: number; maxLength?: number; pattern?: string }
export type PolicyReadiness = { status: string; contract_version: number | null; posting_eligible: false; reason: string; sections: Record<string, { status: string; missing_fields: string[]; reason: string; posting_eligible: false }>; contexts?: Record<string, { policy_ready: boolean; posting_eligible: false; posting_status: string; blocked_policies: string[] }> }
// Exact hundredths of a percentage point; only UX validation, backend revalidates.
export function shareValid(share: Share) {
  const points = (value: string) => {
    if (!/^\d{1,3}(\.\d{1,2})?$/.test(value)) return null
    const [whole, fraction = ''] = value.split('.')
    return Number(whole) * 100 + Number(fraction.padEnd(2, '0'))
  }
  const gym = points(share.gym_percent), fitigo = points(share.fitigo_percent)
  return gym !== null && fitigo !== null && gym <= 10000 && fitigo <= 10000 && gym + fitigo === 10000
}