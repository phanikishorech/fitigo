import type {
  CreateAccessBookingRequest,
  CreateAccessBookingResponse,
  CartItemCreateClassRequest,
  CartItemCreateGymRequest,
  CartItemResponse,
  ListCartItemsResponse,
  CartCheckoutResponse,
  ClassSessionPublicResponse,
  GymBookingOptionsResponse,
  OperatingHoursForDateResponse,
  ValidateBookingRequest,
  ValidateBookingResponse
} from './types'
import { authFetch } from '../../auth'

export async function fetchBookingOptions(gymId: number): Promise<GymBookingOptionsResponse> {
  // Use authFetch so membership banner + included flags reflect the logged-in user.
  const r = await authFetch(`/api/v1/gyms/${gymId}/booking-options`)
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data?.detail ?? 'Failed to load booking options')
  }
  return (await r.json()) as GymBookingOptionsResponse
}

export async function validateBooking(gymId: number, body: ValidateBookingRequest): Promise<ValidateBookingResponse> {
  const r = await authFetch(`/api/v1/gyms/${gymId}/validate-booking`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    const detail = data?.detail
    if (typeof detail === 'string' && detail.trim()) throw new Error(detail)
    if (Array.isArray(detail)) {
      // FastAPI validation errors often return a list of objects; stringifying directly renders [object Object]
      const msg = detail
        .map((d: any) => d?.msg ?? d?.message ?? (typeof d === 'string' ? d : null))
        .filter(Boolean)
        .join('; ')
      throw new Error(msg || 'Unable to validate booking')
    }
    throw new Error('Unable to validate booking')
  }
  return (await r.json()) as ValidateBookingResponse
}

export async function createAccessBookings(
  gymId: number,
  body: CreateAccessBookingRequest
): Promise<CreateAccessBookingResponse> {
  const r = await authFetch(`/api/v1/gyms/${gymId}/access-bookings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    const detail = data?.detail
    if (typeof detail === 'string' && detail.trim()) throw new Error(detail)
    if (Array.isArray(detail)) {
      const msg = detail
        .map((d: any) => d?.msg ?? d?.message ?? (typeof d === 'string' ? d : null))
        .filter(Boolean)
        .join('; ')
      throw new Error(msg || 'Unable to create booking')
    }
    throw new Error('Unable to create booking')
  }
  return (await r.json()) as CreateAccessBookingResponse
}

export async function fetchOperatingHoursForDate(gymId: number, date: string): Promise<OperatingHoursForDateResponse> {
  const r = await fetch(`/api/v1/gyms/${gymId}/operating-hours?date=${encodeURIComponent(date)}`)
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data?.detail ?? 'Failed to load operating hours')
  }
  return (await r.json()) as OperatingHoursForDateResponse
}

export async function fetchClassSessions(gymId: number, date: string): Promise<ClassSessionPublicResponse[]> {
  const r = await fetch(`/api/v1/gyms/${gymId}/class-sessions?date=${encodeURIComponent(date)}`)
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data?.detail ?? 'Failed to load classes')
  }
  return (await r.json()) as ClassSessionPublicResponse[]
}

export async function addGymToCart(body: CartItemCreateGymRequest): Promise<CartItemResponse> {
  // Use authFetch so cart belongs to the logged-in user (if any).
  // In dev/demo mode without auth, authFetch behaves like fetch.
  const r = await authFetch(`/api/v1/cart/items/gym`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    const detail = data?.detail
    if (typeof detail === 'string' && detail.trim()) throw new Error(detail)
    throw new Error('Unable to add to cart')
  }
  return (await r.json()) as CartItemResponse
}

export async function addClassToCart(body: CartItemCreateClassRequest): Promise<CartItemResponse> {
  const r = await authFetch(`/api/v1/cart/items/class`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    const detail = data?.detail
    if (typeof detail === 'string' && detail.trim()) throw new Error(detail)
    throw new Error('Unable to add to cart')
  }
  return (await r.json()) as CartItemResponse
}

export async function fetchCartItems(): Promise<ListCartItemsResponse> {
  const r = await authFetch(`/api/v1/cart/items`)
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data?.detail ?? 'Failed to load cart')
  }
  return (await r.json()) as ListCartItemsResponse
}

export async function removeCartItem(itemId: number): Promise<void> {
  const r = await authFetch(`/api/v1/cart/items/${itemId}`, { method: 'DELETE' })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data?.detail ?? 'Failed to remove cart item')
  }
}

export async function checkoutCart(): Promise<CartCheckoutResponse> {
  const r = await authFetch(`/api/v1/cart/checkout`, { method: 'POST' })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data?.detail ?? 'Failed to checkout cart')
  }
  return (await r.json()) as CartCheckoutResponse
}

export async function checkoutCartWithWallet(): Promise<any> {
  const r = await authFetch(`/api/v1/cart/checkout/wallet`, { method: 'POST' })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data?.detail ?? 'Failed to pay with wallet')
  }
  return (await r.json()) as any
}
