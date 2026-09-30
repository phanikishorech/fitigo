import { request, post } from '../../services/client'

// Verified against backend/app/routers/admin.py; shared transport only.
export type AdminDashboardSummary = {
  users: { total: number; customers: number; gym_owners: number }
  gyms: { total: number; pending_approval: number }
  bookings: { today: number; upcoming: number }
  revenue: { last_30d: string; currency: string }
}
export type AdminUserListItem = {
  id: number; first_name: string | null; last_name: string | null; email: string
  phone: string | null; status: string; created_at: string; roles: string[]
}
export type AdminGymListItem = {
  id: number; owner_user_id?: number; name: string; city: string | null; status: string
  is_active: boolean; is_featured?: boolean; created_at: string
}
export type AdminBooking = {
  id: number; status: string; slot_date: string; quantity: number; total_price: string; currency: string
  customer: { id: number; first_name: string | null; last_name: string | null; email: string; phone: string | null }
  gym: { id: number; name: string; city: string | null; status: string; is_active: boolean; owner_user_id: number }
  slot: { id: number; name: string; start_time: string; end_time: string }
  payment: { id: number; provider: string; status: string; amount: string; currency: string; external_ref: string | null } | null
}
export type UserFilters = { q?: string; role?: string; status?: string; limit?: number; offset?: number }
export type GymFilters = { q?: string; status?: string; owner_user_id?: number; is_active?: boolean; featured?: boolean; limit?: number; offset?: number }
export type BookingFilters = { q?: string; gym_id?: number; owner_user_id?: number; date?: string; status?: string; payment_status?: string; limit?: number; offset?: number }
export function query(params: object) {
  const result = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== null && value !== '') result.set(key, String(value)) })
  return result.size ? `?${result}` : ''
}
type GymResult = { status: string; gym_id: number; new_status: string }
export const adminPing = () => request<{ status: string; user_id: number }>('/admin/ping')
export const fetchAdminDashboardSummary = () => request<AdminDashboardSummary>('/admin/dashboard/summary')
export const fetchAdminUsers = (params: UserFilters = {}) => request<AdminUserListItem[]>(`/admin/users${query(params)}`)
export const fetchAdminUser = (id: number) => request<AdminUserListItem>(`/admin/users/${id}`)
export const adminUpdateUserStatus = (id: number, payload: { status: string; reason?: string | null }) => post<{ status: string; user_id: number; new_status: string }>(`/admin/users/${id}/status`, payload)
export const fetchPendingGyms = () => request<AdminGymListItem[]>('/admin/gyms/pending')
export const fetchAdminGyms = (params: GymFilters = {}) => request<AdminGymListItem[]>(`/admin/gyms${query(params)}`)
export const adminApproveGym = (id: number) => post<GymResult>(`/admin/gyms/${id}/approve`)
export const adminRejectGym = (id: number, reason: string) => post<GymResult>(`/admin/gyms/${id}/reject`, { reason })
export const adminSuspendGym = (id: number, reason: string) => post<GymResult>(`/admin/gyms/${id}/suspend`, { reason })
export const adminReactivateGym = (id: number) => post<GymResult>(`/admin/gyms/${id}/reactivate`)
export const adminSetGymFeatured = (id: number, featured: boolean) => post<{ status: string; gym_id: number; is_featured: boolean }>(`/admin/gyms/${id}/feature?featured=${featured}`)
export const fetchAdminBookings = (params: BookingFilters = {}) => request<AdminBooking[]>(`/admin/bookings${query(params)}`)
export const fetchAdminBooking = (id: number) => request<AdminBooking>(`/admin/bookings/${id}`)
export const adminCancelBooking = (id: number, reason: string) => post<{ status: string; booking_id: number; new_status: string }>(`/admin/bookings/${id}/cancel`, { reason: reason.trim() || null })