import { request } from '../../services/client'

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
  rejection_reason?: string | null
  can_submit_for_approval?: boolean
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

export type SlotAvailability = OwnerSlot & { availability: { slot_date: string; status: string; capacity_total: number; booked_count: number; blocked_count: number; remaining_capacity: number } }
export const listPublicSlotAvailability = (gymId: number, date: string) => request<SlotAvailability[]>(`/gyms/${gymId}/slots?date=${encodeURIComponent(date)}`)

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
  allowed_actions?: ('MARK_ATTENDED' | 'MARK_NO_SHOW' | 'CANCEL')[]
  cancellation_policy?: string
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


export async function fetchMyRoles(): Promise<string[]> {
  const r = await request<unknown>('/users/me/roles')
  return r as string[]
}

export async function fetchOwnerSummary(): Promise<OwnerDashboardSummary> {
  const r = await request<unknown>('/gym-owner/dashboard/summary')
  return r as OwnerDashboardSummary
}

export async function fetchOwnerGyms(): Promise<OwnerGymListItem[]> {
  const r = await request<unknown>('/gym-owner/gyms')
  return r as OwnerGymListItem[]
}

export async function fetchGymDetailsOwner(gymId: number): Promise<OwnerGymDetails> {
  const r = await request<unknown>(`/gym-owner/gyms/${gymId}`)
  return r as OwnerGymDetails
}

export async function updateGymOwner(gymId: number, patch: Partial<OwnerGymDetails>): Promise<OwnerGymDetails> {
  const r = await request<unknown>(`/gym-owner/gyms/${gymId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch)
  })
  return r as OwnerGymDetails
}

export async function createGymOwner(payload: {
  name: string
  city?: string | null
  description?: string | null
  gym_price_per_person?: string
  has_classes?: boolean
}): Promise<OwnerGymDetails> {
  const r = await request<unknown>('/gym-owner/gyms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  return r as OwnerGymDetails
}

export async function submitGymForApproval(gymId: number): Promise<{ status: string; gym_id: number; new_status: string }> {
  return request(`/gym-owner/gyms/${gymId}/submit`, { method: 'POST' })
}

export async function fetchFacilities(): Promise<Facility[]> {
  return request<Facility[]>('/facilities')
}

export async function setGymFacilities(gymId: number, facilityIds: number[]): Promise<void> {
  const r = await request<unknown>(`/gym-owner/gyms/${gymId}/facilities`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ facility_ids: facilityIds })
  })
  void r
}

export async function setOperatingHours(gymId: number, items: OperatingHourItem[]): Promise<void> {
  const r = await request<unknown>(`/gym-owner/gyms/${gymId}/operating-hours`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items })
  })
  void r
}

export async function uploadGymImage(gymId: number, file: File, isCover: boolean): Promise<{ status: string; image_id: number; file_path: string; url: string }> {
  const fd = new FormData()
  fd.append('file', file)
  return request(`/gym-owner/gyms/${gymId}/images?is_cover=${encodeURIComponent(String(isCover))}`, {
    method: 'POST',
    body: fd
  })
}

export async function setCoverImage(gymId: number, imageId: number): Promise<void> {
  const r = await request<unknown>(`/gym-owner/gyms/${gymId}/images/${imageId}/set-cover`, { method: 'PUT' })
  void r
}

export async function listOwnerSlots(gymId: number): Promise<OwnerSlot[]> {
  return request(`/gym-owner/gyms/${gymId}/slots`)
}

export async function listOwnerMembershipPlans(gymId: number): Promise<OwnerMembershipPlan[]> {
  return request(`/gym-owner/gyms/${gymId}/membership-plans`)
}

export async function createOwnerMembershipPlan(
  gymId: number,
  payload: { name: string; description?: string | null; duration_days: number; price: string; currency?: string }
): Promise<OwnerMembershipPlan> {
  return request(`/gym-owner/gyms/${gymId}/membership-plans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}

export async function updateOwnerMembershipPlan(
  planId: number,
  patch: { name?: string; description?: string | null; duration_days?: number; price?: string; currency?: string; is_active?: boolean }
): Promise<OwnerMembershipPlan> {
  return request(`/gym-owner/membership-plans/${planId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch)
  })
}

export async function deactivateOwnerMembershipPlan(planId: number): Promise<void> {
  const r = await request<unknown>(`/gym-owner/membership-plans/${planId}`, { method: 'DELETE' })
  void r
}

export async function activateOwnerMembershipPlan(planId: number): Promise<void> {
  const r = await request<unknown>(`/gym-owner/membership-plans/${planId}/activate`, { method: 'POST' })
  void r
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
  const r = await request<unknown>(`/gym-owner/gyms/${gymId}/slots`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  void r
}

export async function updateOwnerSlot(slotId: number, patch: { name?: string; start_time?: string; end_time?: string; capacity?: number; price?: string; is_active?: boolean }): Promise<void> {
  const r = await request<unknown>(`/gym-owner/slots/${slotId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch)
  })
  void r
}

export async function deactivateOwnerSlot(slotId: number): Promise<void> {
  const r = await request<unknown>(`/gym-owner/slots/${slotId}`, { method: 'DELETE' })
  void r
}

export async function listStaff(gymId: number): Promise<StaffAssignment[]> {
  return request(`/gym-owner/gyms/${gymId}/staff`)
}

export async function inviteStaff(gymId: number, payload: { email: string; first_name?: string | null; last_name?: string | null }): Promise<{ status: string; assignment_id: number; staff_user_id: number; temp_password: string | null }> {
  return request(`/gym-owner/gyms/${gymId}/staff/invite`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}

export async function removeStaff(gymId: number, userId: number): Promise<void> {
  const r = await request<unknown>(`/gym-owner/gyms/${gymId}/staff/${userId}`, { method: 'DELETE' })
  void r
}

export async function listBookings(gymId: number, params?: { date?: string; status?: string; limit?: number; offset?: number }): Promise<OwnerBooking[]> {
  const qs = new URLSearchParams()
  if (params?.date) qs.set('date', params.date)
  if (params?.status) qs.set('status', params.status)
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.offset) qs.set('offset', String(params.offset))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return request(`/gym-owner/gyms/${gymId}/bookings${suffix}`)
}

export async function bookingCancel(bookingId: number, reason?: string): Promise<void> {
  const r = await request<unknown>(`/gym-owner/bookings/${bookingId}/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: reason ?? 'Owner cancelled' })
  })
  void r
}

export async function bookingMarkAttended(bookingId: number, note?: string): Promise<void> {
  const r = await request<unknown>(`/gym-owner/bookings/${bookingId}/mark-attended`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note: note ?? null })
  })
  void r
}

export async function bookingMarkNoShow(bookingId: number, note?: string): Promise<void> {
  const r = await request<unknown>(`/gym-owner/bookings/${bookingId}/mark-no-show`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note: note ?? null })
  })
  void r
}
