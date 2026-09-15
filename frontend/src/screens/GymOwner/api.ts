import { authFetch } from '../../auth'

export type OwnerDashboardSummary = {
  gyms: { total: number; approved: number; pending_approval: number; draft: number }
  bookings: { today: number; upcoming: number }
  revenue: { last_30d: string; currency: string }
}

export type OwnerGymListItem = {
  id: number
  name: string
  city: string | null
  status: string
  is_active: boolean
  created_at: string
  cover_image_url?: string | null
}

export type GymImage = {
  id: number
  file_path: string
  original_filename: string | null
  image_type: string | null
  display_order: number
  is_cover: boolean
  created_at: string
}

export type Facility = { id: number; name: string; description: string | null; icon: string | null }

export type OperatingHourItem = { day_of_week: number; open_time: string | null; close_time: string | null; is_closed: boolean }

export type OwnerGymDetails = {
  id: number
  owner_user_id: number
  name: string
  description: string | null
  phone: string | null
  email: string | null
  address_line_1: string | null
  address_line_2: string | null
  city: string | null
  state: string | null
  country: string | null
  postal_code: string | null
  latitude: string | null
  longitude: string | null
  status: string
  is_active: boolean

  gym_price_per_person?: string
  has_classes?: boolean
  created_at: string
  updated_at: string
  images: GymImage[]
  facilities: Facility[]
  operating_hours: OperatingHourItem[]
}

export type OwnerSlot = {
  id: number
  gym_id: number
  name: string
  start_time: string
  end_time: string
  capacity: number
  price: string
  is_active: boolean
}

export type StaffAssignment = { id: number; gym_id: number; user_id: number; role: string }

export type OwnerMembershipPlan = {
  id: number
  gym_id: number
  name: string
  description: string | null
  duration_days: number
  price: string
  currency: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export type OwnerBooking = {
  id: number
  gym_id: number
  gym_slot_id: number
  slot_date: string
  quantity: number
  unit_price: string
  total_price: string
  currency: string
  status: string
  notes: string | null
  expires_at: string
  expired_at: string | null
  created_at: string
  updated_at: string
  cancelled_at: string | null
  attendance_status: string | null
  attendance_marked_at: string | null
  attendance_note: string | null
  customer: { id: number; first_name: string | null; last_name: string | null; email: string; phone: string | null }
  slot: { id: number; name: string; start_time: string; end_time: string }
  payment: { id: number; provider: string; status: string; amount: string; currency: string; external_ref: string | null } | null
}

async function jsonOrThrow<T>(r: Response): Promise<T> {
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error((data as any)?.detail ?? 'Request failed')
  return data as T
}

export async function fetchMyRoles(): Promise<string[]> {
  const r = await authFetch('/api/v1/users/me/roles')
  return jsonOrThrow<string[]>(r)
}

export async function fetchOwnerSummary(): Promise<OwnerDashboardSummary> {
  const r = await authFetch('/api/v1/gym-owner/dashboard/summary')
  return jsonOrThrow<OwnerDashboardSummary>(r)
}

export async function fetchOwnerGyms(): Promise<OwnerGymListItem[]> {
  const r = await authFetch('/api/v1/gym-owner/gyms')
  return jsonOrThrow<OwnerGymListItem[]>(r)
}

export async function fetchGymDetailsOwner(gymId: number): Promise<OwnerGymDetails> {
  const r = await authFetch(`/api/v1/gym-owner/gyms/${gymId}`)
  return jsonOrThrow<OwnerGymDetails>(r)
}

export async function updateGymOwner(gymId: number, patch: Partial<OwnerGymDetails>): Promise<OwnerGymDetails> {
  const r = await authFetch(`/api/v1/gym-owner/gyms/${gymId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch)
  })
  return jsonOrThrow<OwnerGymDetails>(r)
}

export async function createGymOwner(payload: {
  name: string
  city?: string | null
  description?: string | null
  gym_price_per_person?: string
  has_classes?: boolean
}): Promise<OwnerGymDetails> {
  const r = await authFetch('/api/v1/gym-owner/gyms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  return jsonOrThrow<OwnerGymDetails>(r)
}

export async function submitGymForApproval(gymId: number): Promise<{ status: string; gym_id: number; new_status: string }> {
  const r = await authFetch(`/api/v1/gym-owner/gyms/${gymId}/submit`, { method: 'POST' })
  return jsonOrThrow(r)
}

export async function fetchFacilities(): Promise<Facility[]> {
  const r = await fetch('/api/v1/facilities')
  const data = await r.json().catch(() => ([] as any))
  if (!r.ok) throw new Error((data as any)?.detail ?? 'Failed to load facilities')
  return data as Facility[]
}

export async function setGymFacilities(gymId: number, facilityIds: number[]): Promise<void> {
  const r = await authFetch(`/api/v1/gym-owner/gyms/${gymId}/facilities`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ facility_ids: facilityIds })
  })
  await jsonOrThrow(r)
}

export async function setOperatingHours(gymId: number, items: OperatingHourItem[]): Promise<void> {
  const r = await authFetch(`/api/v1/gym-owner/gyms/${gymId}/operating-hours`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items })
  })
  await jsonOrThrow(r)
}

export async function uploadGymImage(gymId: number, file: File, isCover: boolean): Promise<{ status: string; image_id: number; file_path: string; url: string }> {
  const fd = new FormData()
  fd.append('file', file)
  const r = await authFetch(`/api/v1/gym-owner/gyms/${gymId}/images?is_cover=${encodeURIComponent(String(isCover))}`, {
    method: 'POST',
    body: fd
  })
  return jsonOrThrow(r)
}

export async function setCoverImage(gymId: number, imageId: number): Promise<void> {
  const r = await authFetch(`/api/v1/gym-owner/gyms/${gymId}/images/${imageId}/set-cover`, { method: 'PUT' })
  await jsonOrThrow(r)
}

export async function listOwnerSlots(gymId: number): Promise<OwnerSlot[]> {
  const r = await authFetch(`/api/v1/gym-owner/gyms/${gymId}/slots`)
  return jsonOrThrow(r)
}

export async function listOwnerMembershipPlans(gymId: number): Promise<OwnerMembershipPlan[]> {
  const r = await authFetch(`/api/v1/gym-owner/gyms/${gymId}/membership-plans`)
  return jsonOrThrow(r)
}

export async function createOwnerMembershipPlan(
  gymId: number,
  payload: { name: string; description?: string | null; duration_days: number; price: string; currency?: string }
): Promise<OwnerMembershipPlan> {
  const r = await authFetch(`/api/v1/gym-owner/gyms/${gymId}/membership-plans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  return jsonOrThrow(r)
}

export async function updateOwnerMembershipPlan(
  planId: number,
  patch: { name?: string; description?: string | null; duration_days?: number; price?: string; currency?: string; is_active?: boolean }
): Promise<OwnerMembershipPlan> {
  const r = await authFetch(`/api/v1/gym-owner/membership-plans/${planId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch)
  })
  return jsonOrThrow(r)
}

export async function deactivateOwnerMembershipPlan(planId: number): Promise<void> {
  const r = await authFetch(`/api/v1/gym-owner/membership-plans/${planId}`, { method: 'DELETE' })
  await jsonOrThrow(r)
}

export async function activateOwnerMembershipPlan(planId: number): Promise<void> {
  const r = await authFetch(`/api/v1/gym-owner/membership-plans/${planId}/activate`, { method: 'POST' })
  await jsonOrThrow(r)
}

export async function createOwnerSlot(
  gymId: number,
  payload: {
    name: string
    start_time: string
    end_time: string
    capacity: number
    price: string
    specific_date?: string | null
    repeat_days?: number[]
  }
): Promise<void> {
  const r = await authFetch(`/api/v1/gym-owner/gyms/${gymId}/slots`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  await jsonOrThrow(r)
}

export async function updateOwnerSlot(slotId: number, patch: { name?: string; start_time?: string; end_time?: string; capacity?: number; price?: string; is_active?: boolean }): Promise<void> {
  const r = await authFetch(`/api/v1/gym-owner/slots/${slotId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch)
  })
  await jsonOrThrow(r)
}

export async function deactivateOwnerSlot(slotId: number): Promise<void> {
  const r = await authFetch(`/api/v1/gym-owner/slots/${slotId}`, { method: 'DELETE' })
  await jsonOrThrow(r)
}

export async function listStaff(gymId: number): Promise<StaffAssignment[]> {
  const r = await authFetch(`/api/v1/gym-owner/gyms/${gymId}/staff`)
  return jsonOrThrow(r)
}

export async function inviteStaff(gymId: number, payload: { email: string; first_name?: string | null; last_name?: string | null }): Promise<{ status: string; assignment_id: number; staff_user_id: number; temp_password: string | null }> {
  const r = await authFetch(`/api/v1/gym-owner/gyms/${gymId}/staff/invite`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  return jsonOrThrow(r)
}

export async function removeStaff(gymId: number, userId: number): Promise<void> {
  const r = await authFetch(`/api/v1/gym-owner/gyms/${gymId}/staff/${userId}`, { method: 'DELETE' })
  await jsonOrThrow(r)
}

export async function listBookings(gymId: number, params?: { date?: string; status?: string }): Promise<OwnerBooking[]> {
  const qs = new URLSearchParams()
  if (params?.date) qs.set('date', params.date)
  if (params?.status) qs.set('status', params.status)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const r = await authFetch(`/api/v1/gym-owner/gyms/${gymId}/bookings${suffix}`)
  return jsonOrThrow(r)
}

export async function bookingCancel(bookingId: number, reason?: string): Promise<void> {
  const r = await authFetch(`/api/v1/gym-owner/bookings/${bookingId}/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: reason ?? 'Owner cancelled' })
  })
  await jsonOrThrow(r)
}

export async function bookingMarkAttended(bookingId: number, note?: string): Promise<void> {
  const r = await authFetch(`/api/v1/gym-owner/bookings/${bookingId}/mark-attended`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note: note ?? null })
  })
  await jsonOrThrow(r)
}

export async function bookingMarkNoShow(bookingId: number, note?: string): Promise<void> {
  const r = await authFetch(`/api/v1/gym-owner/bookings/${bookingId}/mark-no-show`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note: note ?? null })
  })
  await jsonOrThrow(r)
}
