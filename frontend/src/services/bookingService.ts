import type { CartItemCreateClassRequest, CartItemCreateGymRequest, CartItemResponse, ClassSessionPublicResponse, GymBookingOptionsResponse, OperatingHoursForDateResponse } from '../screens/GymAccess/types'
import type { CartWalletCheckoutResponse } from '../screens/Checkout/api'
import { post, request } from './client'

export type Visit = {
  booking_id: number; booking_status: string; attendance_status: string | null; gym_id: number; gym_name: string;
  gym_location: string; access_type: string; class_name: string | null; visit_date: string; start_time: string;
  end_time: string; membership_covered: boolean; amount_paid: string | null; currency: string; booking_created_at: string
}
export type Booking = {
  id: number; gym_id: number; slot_date: string; quantity: number; total_price: string; currency: string;
  status: string; notes: string | null; cancelled_at: string | null;
  payment: { status: string; amount: string; currency: string; provider: string } | null
}
export const bookingService = {
  options: (id: number) => request<GymBookingOptionsResponse>(`/gyms/${id}/booking-options`),
  hours: (id: number, date: string) => request<OperatingHoursForDateResponse>(`/gyms/${id}/operating-hours?date=${encodeURIComponent(date)}`),
  sessions: (id: number, date: string) => request<ClassSessionPublicResponse[]>(`/gyms/${id}/class-sessions?date=${encodeURIComponent(date)}`),
  addGym: (body: CartItemCreateGymRequest) => post<CartItemResponse>('/cart/items/gym', body),
  addClass: (body: CartItemCreateClassRequest) => post<CartItemResponse>('/cart/items/class', body),
  cart: () => request<CartItemResponse[]>('/cart/items'),
  remove: (id: number) => request<{ deleted?: boolean }>(`/cart/items/${id}`, { method: 'DELETE' }),
  pay: () => post<CartWalletCheckoutResponse>('/cart/checkout/wallet'),
  visits: (status: 'all' | 'upcoming' | 'past' | 'cancelled' = 'all') => request<Visit[]>(`/profile/bookings?status=${status}`),
  detail: (id: number) => request<Booking>(`/bookings/${id}`),
  cancel: (id: number) => post<Booking>(`/bookings/${id}/cancel`, { reason: 'Cancelled by customer' })
}