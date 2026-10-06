import { request } from './client'
export type PausePeriod = { id: number; start_date: string; end_date: string; resumes_on: string; days: number; status: string; previous_end_at: string; new_end_at: string }
export type PauseEligibility = {
  membership_id: number; membership_status: string; pause_allowed: boolean; can_pause: boolean
  max_pause_days: number; pause_days_used: number; pause_days_remaining: number; currently_paused: boolean
  eligible_from: string | null; eligible_until: string | null; original_end_at: string; current_end_at: string
  current_pause: PausePeriod | null; history: PausePeriod[]; reason_code: string | null; timezone: string
}
export type PauseSelection = { start_date: string; days: number }
export type PausePreview = PauseSelection & { membership_id: number; end_date: string; resumes_on: string; current_end_at: string; new_end_at: string; pause_days_remaining_after: number; preview_token: string }
export const membershipPauseService = {
  eligibility: (id: number) => request<PauseEligibility>(`/memberships/me/${id}/pause`, { cache: 'no-store' }),
  preview: (id: number, selection: PauseSelection) => request<PausePreview>(`/memberships/me/${id}/pause/preview`, { method: 'POST', body: JSON.stringify(selection), cache: 'no-store' }),
  confirm: (id: number, preview: PausePreview, key: string) => request<PauseEligibility>(`/memberships/me/${id}/pause`, { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify({ start_date: preview.start_date, days: preview.days, accepted_preview: preview.preview_token }), cache: 'no-store' }),
}