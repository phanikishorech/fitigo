import { logoutSession } from '../session/store'
import { ApiError, request } from '../services/client'
import { authService } from '../services/authService'
import { query } from '../screens/Admin/api'
import type { OwnerGymDetails } from '../screens/GymOwner/api'

export const adminAuthService = {
  login: authService.loginWithPassword,
  logout: logoutSession
}
export type DailyReport = { day: string; total_bookings: number; confirmed_bookings: number; cancelled_bookings: number; expired_bookings: number; paid_amount_total: string }
export type ReportFilters = { date_from?: string; date_to?: string; gym_id?: number; limit?: number }
export const dashboardService = { daily: (params: ReportFilters) => request<DailyReport[]>(`/admin/reports/bookings/daily${query(params)}`) }
export type AdminGymDetails = Omit<OwnerGymDetails, 'can_submit_for_approval'> & {
  allowed_actions: ('APPROVE' | 'REJECT')[]
  review_history: { id: number; old_status: string; new_status: string; reason: string | null; created_at: string }[]
}
export const gymService = {
  details: (id: number, signal?: AbortSignal) => request<AdminGymDetails>(`/admin/gyms/${id}`, { signal, cache: 'no-store' })
}
export type AdminNotification = { id: number; event_type: string; status: string; created_at: string }
export const notificationService = { list: (offset: number) => request<AdminNotification[]>(`/notifications/me?limit=21&offset=${offset}`) }
export function adminError(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Unable to complete this request. Please try again.'
  if (error.status === 0) return 'Unable to connect. Check your internet connection and try again.'
  if (error.status === 401) return 'Your session has expired. Please sign in again.'
  if (error.status === 403) return "Access denied. You don't have permission to access this resource."
  if (error.status === 404) return 'This record could not be found. It may have been removed.'
  if (error.status === 400 || error.status === 409) return 'This action could not be completed. The record may have changed. Refresh and try again.'
  if (error.status === 422) return 'Please check the entered values and try again.'
  if (error.status === 429) return 'Too many attempts. Please wait a moment and try again.'
  return 'Something went wrong. Please try again shortly.'
}