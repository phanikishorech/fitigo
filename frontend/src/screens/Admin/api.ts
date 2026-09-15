import { authFetch } from '../../auth'

async function jsonOrThrow<T>(r: Response): Promise<T> {
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error((data as any)?.detail ?? 'Request failed')
  return data as T
}

export type AdminDashboardSummary = {
  users: { total: number; customers: number; gym_owners: number }
  gyms: { total: number; pending_approval: number }
  bookings: { today: number; upcoming: number }
  revenue: { last_30d: string; currency: string }
}

export type AdminUserListItem = {
  id: number
  first_name: string | null
  last_name: string | null
  email: string
  phone: string | null
  status: string
  created_at: string
  roles: string[]
}

export type AdminGymListItem = {
  id: number
  owner_user_id?: number
  name: string
  city: string | null
  status: string
  is_active: boolean
  is_featured?: boolean
  created_at: string
}

export type AdminBooking = {
  id: number
  status: string
  slot_date: string
  quantity: number
  total_price: string
  currency: string
  customer: { id: number; first_name: string | null; last_name: string | null; email: string; phone: string | null }
  gym: { id: number; name: string; city: string | null; status: string; is_active: boolean; owner_user_id: number }
  slot: { id: number; name: string; start_time: string; end_time: string }
  payment: { id: number; provider: string; status: string; amount: string; currency: string; external_ref: string | null } | null
}

export async function adminPing(): Promise<{ status: string } & Record<string, any>> {
  const r = await authFetch('/api/v1/admin/ping')
  return jsonOrThrow(r)
}

export async function fetchAdminDashboardSummary(): Promise<AdminDashboardSummary> {
  const r = await authFetch('/api/v1/admin/dashboard/summary')
  return jsonOrThrow(r)
}

export async function fetchAdminUsers(params: { q?: string; role?: string; status?: string; limit?: number; offset?: number } = {}): Promise<AdminUserListItem[]> {
  const usp = new URLSearchParams()
  if (params.q) usp.set('q', params.q)
  if (params.role) usp.set('role', params.role)
  if (params.status) usp.set('status', params.status)
  if (typeof params.limit === 'number') usp.set('limit', String(params.limit))
  if (typeof params.offset === 'number') usp.set('offset', String(params.offset))
  const url = `/api/v1/admin/users${usp.toString() ? `?${usp.toString()}` : ''}`
  const r = await authFetch(url)
  return jsonOrThrow(r)
}

export async function adminUpdateUserStatus(userId: number, payload: { status: string; reason?: string | null }): Promise<{ status: string; user_id: number; new_status: string }> {
  const r = await authFetch(`/api/v1/admin/users/${userId}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  return jsonOrThrow(r)
}

export async function fetchPendingGyms(): Promise<AdminGymListItem[]> {
  const r = await authFetch('/api/v1/admin/gyms/pending')
  return jsonOrThrow(r)
}

export async function fetchAdminGyms(params: { q?: string; status?: string; owner_user_id?: number; is_active?: boolean; featured?: boolean; limit?: number; offset?: number } = {}): Promise<AdminGymListItem[]> {
  const usp = new URLSearchParams()
  if (params.q) usp.set('q', params.q)
  if (params.status) usp.set('status', params.status)
  if (typeof params.owner_user_id === 'number') usp.set('owner_user_id', String(params.owner_user_id))
  if (typeof params.is_active === 'boolean') usp.set('is_active', String(params.is_active))
  if (typeof params.featured === 'boolean') usp.set('featured', String(params.featured))
  if (typeof params.limit === 'number') usp.set('limit', String(params.limit))
  if (typeof params.offset === 'number') usp.set('offset', String(params.offset))
  const url = `/api/v1/admin/gyms${usp.toString() ? `?${usp.toString()}` : ''}`
  const r = await authFetch(url)
  return jsonOrThrow(r)
}

export async function adminSetGymFeatured(gymId: number, featured: boolean): Promise<{ status: string; gym_id: number; is_featured: boolean }> {
  const r = await authFetch(`/api/v1/admin/gyms/${gymId}/feature?featured=${encodeURIComponent(String(featured))}`, {
    method: 'POST'
  })
  return jsonOrThrow(r)
}

export async function adminApproveGym(gymId: number): Promise<{ status: string; gym_id: number; new_status: string }> {
  const r = await authFetch(`/api/v1/admin/gyms/${gymId}/approve`, { method: 'POST' })
  return jsonOrThrow(r)
}

export async function adminRejectGym(gymId: number, reason: string): Promise<{ status: string; gym_id: number; new_status: string }> {
  const r = await authFetch(`/api/v1/admin/gyms/${gymId}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason })
  })
  return jsonOrThrow(r)
}

export async function adminSuspendGym(gymId: number, reason: string): Promise<{ status: string; gym_id: number; new_status: string }> {
  const r = await authFetch(`/api/v1/admin/gyms/${gymId}/suspend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason })
  })
  return jsonOrThrow(r)
}

export async function adminReactivateGym(gymId: number): Promise<{ status: string; gym_id: number; new_status: string }> {
  const r = await authFetch(`/api/v1/admin/gyms/${gymId}/reactivate`, { method: 'POST' })
  return jsonOrThrow(r)
}

export async function fetchAdminBookings(params: { q?: string; gym_id?: number; owner_user_id?: number; date?: string; status?: string; payment_status?: string; limit?: number; offset?: number } = {}): Promise<AdminBooking[]> {
  const usp = new URLSearchParams()
  if (params.q) usp.set('q', params.q)
  if (typeof params.gym_id === 'number') usp.set('gym_id', String(params.gym_id))
  if (typeof params.owner_user_id === 'number') usp.set('owner_user_id', String(params.owner_user_id))
  if (params.date) usp.set('date', params.date)
  if (params.status) usp.set('status', params.status)
  if (params.payment_status) usp.set('payment_status', params.payment_status)
  if (typeof params.limit === 'number') usp.set('limit', String(params.limit))
  if (typeof params.offset === 'number') usp.set('offset', String(params.offset))
  const url = `/api/v1/admin/bookings${usp.toString() ? `?${usp.toString()}` : ''}`
  const r = await authFetch(url)
  return jsonOrThrow(r)
}

export async function adminCancelBooking(bookingId: number, reason: string): Promise<{ status: string; booking_id: number; new_status: string }> {
  const r = await authFetch(`/api/v1/admin/bookings/${bookingId}/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason })
  })
  return jsonOrThrow(r)
}
