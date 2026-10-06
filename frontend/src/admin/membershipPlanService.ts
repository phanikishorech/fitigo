import { ApiError, request } from '../services/client'
import type { PlatformCatalog, PlatformPlan } from '../services/platformMembershipService'
import { adminError } from './services'

export type PlanInput = {
  code: string; name: string; description: string | null; duration_value: number
  duration_unit: PlatformPlan['duration_unit']; base_price: string; currency: 'INR'
  benefits: string[]; badge: string | null; display_order: number; is_active: boolean
  pause_rule?: { allowed: boolean; max_pause_days: number }
}
export type OfferInput = {
  expected_version: number; kind: 'PERCENTAGE' | 'FIXED'; value: string; title: string | null
  starts_at: string; ends_at: string; is_active: boolean
}
export type OfferConfiguration = Omit<OfferInput, 'expected_version'> & { id: number; state: 'ACTIVE' | 'SCHEDULED' | 'EXPIRED' | 'DISABLED' }
export type AdminPlanDetail = { plan: PlatformPlan; offer_configuration: OfferConfiguration | null; server_time: string }
export const adminMembershipPlans = {
  list: (signal?: AbortSignal) => request<PlatformCatalog>('/admin/membership-plans', { cache: 'no-store', signal }),
  detail: (id: number, signal?: AbortSignal) => request<AdminPlanDetail>(`/admin/membership-plans/${id}`, { cache: 'no-store', signal }),
  create: (data: PlanInput) => request<PlatformPlan>('/admin/membership-plans', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: number, data: PlanInput, version: number) => request<PlatformPlan>(`/admin/membership-plans/${id}`, { method: 'PUT', body: JSON.stringify({ ...data, expected_version: version }) }),
  offer: (id: number, data: OfferInput) => request<PlatformPlan>(`/admin/membership-plans/${id}/offer`, { method: 'PUT', body: JSON.stringify(data) }),
}
export function editablePlan(plan: PlatformPlan): PlanInput {
  return { code: plan.code, name: plan.name, description: plan.description, duration_value: plan.duration_value,
    duration_unit: plan.duration_unit, base_price: plan.base_price, currency: 'INR', benefits: [...plan.benefits],
    badge: plan.badge, display_order: plan.display_order, is_active: plan.is_active,
    ...(plan.pause_rule ? { pause_rule: { ...plan.pause_rule } } : {}) }
}
export function planAdminError(error: unknown) {
  if (error instanceof ApiError && error.code === 'PLAN_VERSION_CHANGED') return 'Another administrator changed this plan. Reload the latest version before saving again. Your changes have not been saved.'
  if (error instanceof ApiError && error.code === 'PLAN_CODE_EXISTS') return 'This plan code is already in use. Choose a different code.'
  return adminError(error)
}
export function utcInput(value: string) { return new Date(value).toISOString().slice(0, 19) }
export function utcValue(value: string) { return new Date(`${value}Z`).toISOString() }