// Additional owner contracts. Existing CRUD remains in the existing owner service.
import { post, request } from '../services/client'
import type { OwnerBooking } from '../screens/GymOwner/api'

export const capabilities = {
  members: { available: false, message: 'Member profiles and membership history are not available in the current owner API.' },
  checkins: { available: false, message: 'Check-in history is not available in the current owner API. Recorded booking attendance is shown separately.' },
  gymRevenue: { available: false, message: 'Revenue for an individual gym is not available yet. The backend provides an all-gyms summary only.' },
  trends: { available: false, message: 'Historical analytics are not available yet. No estimated trends or comparisons are shown.' },
  photoManagement: { available: false, message: 'Photos can be uploaded and a cover selected. Removing and reordering saved photos is not supported yet.' },
  bookingActions: { available: false, message: 'The booking API does not provide action eligibility yet. Attendance and cancellation controls are unavailable until the server supplies permitted actions.' }
} as const

export type CheckInResult = { success: true; status: string; customer_name: string; gym_name: string; access_type: string; checkin_time: string } | { success: false; status: string; message: string }
export type Notification = { id: number; event_type: string; status: string; created_at: string }
export const ownerService = {
  register: (body: { first_name: string; last_name: string; email: string; phone: string | null; password: string }) => post<{ id: number; email: string }>('/auth/register/gym-owner', body),
  booking: (id: number) => request<OwnerBooking>(`/gym-owner/bookings/${id}`),
  notifications: (offset: number) => request<Notification[]>(`/notifications/me?limit=20&offset=${offset}`),
  staffGyms: () => request<{ id: number; name: string; city: string | null }[]>('/gym-staff/gyms'),
  checkIn: (gymId: number, token: string, signal?: AbortSignal) => request<CheckInResult>('/checkins/validate', { method: 'POST', body: JSON.stringify({ gym_id: gymId, qr_token: token }), signal }),
}

export function allowedBookingActions(booking: OwnerBooking) {
  // Explicit capabilities only. Status/date must never be used to infer permission.
  return booking.allowed_actions ?? []
}
export function customerName(customer: OwnerBooking['customer']) {
  return [customer.first_name, customer.last_name].filter(Boolean).join(' ') || `Customer #${customer.id}`
}