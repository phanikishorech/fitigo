import type { CancellationPolicy } from '../components/booking/BookingCancellation'
import type { CartItemCreateClassRequest, CartItemCreateGymRequest, CartItemResponse, ClassSessionPublicResponse, GymBookingOptionsResponse, OperatingHoursForDateResponse } from '../screens/GymAccess/types'
import type { CartWalletCheckoutResponse } from '../screens/Checkout/api'
import { post, request } from './client'
import { cartMutation } from './customerActivity'

export type BookingAccess = { access_type: string; status: string; message: string; qr_available: boolean; can_set_visitors: boolean; valid_from?: string | null; expires_at?: string | null; passes: { qr_id: number; status: string; visitor_name?: string | null; checked_in_at?: string | null }[] }
export type BookingQr = { booking_id: number; access_type: string; passes: { qr_id: number; visitor_name: string; status: string; qr_token: string | null; valid_from: string; expires_at: string; checked_in_at?: string | null }[] }
export type Visit = {
  cancellation?: CancellationPolicy | null
  can_review?: boolean; review_id?: number | null; review_rating?: number | null; review_status?: string | null
  booking_access?: BookingAccess
  booking_id: number; booking_status: string; attendance_status: string | null; gym_id: number; gym_name: string;
  gym_location: string; access_type: string; class_name: string | null; visit_date: string; start_time: string;
  end_time: string; membership_covered: boolean; amount_paid: string | null; currency: string; booking_created_at: string
}
export type Booking = {
  cancellation?: CancellationPolicy | null
  visitor_names: string[] | null; access: BookingAccess
  id: number; gym_id: number; slot_date: string; quantity: number; total_price: string; currency: string;
  status: string; notes: string | null; cancelled_at: string | null;
  payment: { status: string; amount: string; currency: string; provider: string } | null
}
export const bookingService = {
  options: (id: number) => request<GymBookingOptionsResponse>(`/gyms/${id}/booking-options`),
  hours: (id: number, date: string) => request<OperatingHoursForDateResponse>(`/gyms/${id}/operating-hours?date=${encodeURIComponent(date)}`),
  sessions: (id: number, date: string) => request<ClassSessionPublicResponse[]>(`/gyms/${id}/class-sessions?date=${encodeURIComponent(date)}`),
  addGym: (body: CartItemCreateGymRequest) => cartMutation(post<CartItemResponse>('/cart/items/gym', body)),
  addClass: (body: CartItemCreateClassRequest) => cartMutation(post<CartItemResponse>('/cart/items/class', body)),
  cart: () => request<CartItemResponse[]>('/cart/items', { cache: 'no-store' }),
  cartItem: (id: number) => request<CartItemResponse>(`/cart/items/${id}`, { cache: 'no-store' }),
  updateCart: (id: number, body: (CartItemCreateGymRequest | CartItemCreateClassRequest) & { expected_updated_at: string }) => cartMutation(request<CartItemResponse>(`/cart/items/${id}`, { method: 'PUT', body: JSON.stringify(body) })),
  remove: (id: number) => cartMutation(request<{ deleted?: boolean }>(`/cart/items/${id}`, { method: 'DELETE' })),
  pay: () => cartMutation(post<CartWalletCheckoutResponse>('/cart/checkout/wallet')),
  visits: (status: 'all' | 'upcoming' | 'past' | 'cancelled' = 'all') => request<Visit[]>(`/profile/bookings?status=${status}&source=individual`, { cache: 'no-store' }),
  visit: (id: number) => request<Visit[]>(`/profile/bookings?status=all&source=individual&booking_id=${id}`, { cache: 'no-store' }),
  detail: (id: number) => request<Booking>(`/bookings/${id}`),
  qr: (id: number) => post<BookingQr>(`/bookings/${id}/qr`),
  visitors: (id: number, visitor_names: string[]) => post<Booking>(`/bookings/${id}/visitors`, { visitor_names }),
  cancel: (id: number, reason?: string) => post<Booking>(`/bookings/${id}/cancel`, { reason: reason || 'Cancelled by customer' })
}