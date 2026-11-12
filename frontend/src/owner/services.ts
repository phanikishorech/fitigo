// Additional owner contracts. Existing CRUD remains in the existing owner service.
import { ApiError, post, request } from '../services/client'
import type { OwnerBooking } from '../screens/GymOwner/api'

export const capabilities = {
  members: { available: true, message: 'Member names and operational history are scoped to the selected gym.' },
  trends: { available: false, message: 'Historical analytics are not available yet. No estimated trends or comparisons are shown.' },
  photoManagement: { available: false, message: 'Reorder photos or select a cover. The cover always displays first. Saved-photo deletion is unavailable until storage and database deletion can be recovered safely.' },
  bookingActions: { available: true, message: 'The server supplies permitted actions and reasons. Use QR check-in instead of manual attendance.' }
} as const

export type CheckInResult = { success: true; status: string; customer_name: string; gym_name: string; access_type: string; access_label?: string; access_source?: string; checkin_time: string } | { success: false; status: string; message: string }
export type Notification = { id: number; event_type: string; status: string; created_at: string }
export const ownerService = {
  register: (body: { first_name: string; last_name: string; email: string; phone: string | null; password: string }) => post<{ id: number; email: string }>('/auth/register/gym-owner', body),
  booking: (id: number) => request<OwnerBooking>(`/gym-owner/bookings/${id}`),
  notifications: (offset: number) => request<Notification[]>(`/notifications/me?limit=20&offset=${offset}`),
  staffGyms: () => request<{ id: number; name: string; city: string | null }[]>('/gym-staff/gyms'),
  checkIn: async (gymId: number, token: string, signal?: AbortSignal): Promise<CheckInResult> => {
    try {
      return await request<CheckInResult>('/checkins/validate', { method: 'POST', body: JSON.stringify({ gym_id: gymId, qr_token: token }), signal })
    } catch (error) {
      // Preserve the scanner's rejection/recovery UX without hiding HTTP 403.
      if (error instanceof ApiError && error.status === 403 && error.code === 'GYM_NOT_ALLOWED') {
        return { success: false, status: error.code, message: error.message }
      }
      throw error
    }
  },
}

export function allowedBookingActions(booking: OwnerBooking) {
  // Explicit capabilities only. Status/date must never be used to infer permission.
  return booking.allowed_actions ?? []
}
export function customerName(customer: OwnerBooking['customer']) {
  return [customer.first_name, customer.last_name].filter(Boolean).join(' ') || `Customer #${customer.id}`
}