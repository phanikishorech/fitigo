import { ApiError, post, request } from '../services/client'
import { profileService } from '../services/accountService'
import { authService } from '../services/authService'
import { clearTokens } from '../auth'
import { clearReadCache } from '../services/readCache'
import { adminPing, fetchAdminGyms, query } from '../screens/Admin/api'
import type { OwnerGymDetails } from '../screens/GymOwner/api'

export const adminAuthService = {
  login: authService.loginWithPassword,
  identity: async () => {
    const [user, roles] = await Promise.all([profileService.me(), request<string[]>('/users/me/roles')])
    if (!roles.some(role => role === 'ADMIN' || role === 'SUPER_ADMIN')) throw new ApiError('Access denied.', 403)
    await adminPing()
    return { user, roles }
  },
  logout: async () => {
    try {
      const refresh = window.localStorage.getItem('fitigo:refresh_token')
      if (refresh) await post('/auth/logout', { refresh_token: refresh })
    } finally { clearTokens(); clearReadCache() }
  }
}
export type DailyReport = { day: string; total_bookings: number; confirmed_bookings: number; cancelled_bookings: number; expired_bookings: number; paid_amount_total: string }
export type ReportFilters = { date_from?: string; date_to?: string; gym_id?: number; limit?: number }
export const dashboardService = { daily: (params: ReportFilters) => request<DailyReport[]>(`/admin/reports/bookings/daily${query(params)}`) }
export const gymService = {
  // No admin detail endpoint exists. Paginate summaries without bypassing owner authorization.
  summary: async (id: number, signal?: AbortSignal) => {
    for (let offset = 0; ; offset += 200) {
      if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
      const rows = await fetchAdminGyms({ limit: 200, offset })
      const gym = rows.find(row => row.id === id)
      if (gym) return gym
      if (rows.length < 200 || rows[rows.length - 1].id < id) throw new ApiError('This gym is no longer available.', 404)
    }
  },
  publicPreview: (id: number) => request<OwnerGymDetails>(`/gyms/${id}`)
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