import type { GymDiscoverResponse } from './types'

export type DiscoverParams = {
  latitude?: number
  longitude?: number
  radius_km?: number
  search?: string
  gym_type?: string
  facilities?: number[]
  min_rating?: number
  open_now?: boolean
  membership_access?: string
  sort_by?: string
  page?: number
  page_size?: number
}

export async function fetchGymTypes(): Promise<string[]> {
  const r = await fetch('/api/v1/meta/gym-types')
  if (!r.ok) throw new Error('Failed to load gym types')
  return (await r.json()) as string[]
}

export async function fetchAppLinks(): Promise<{ android: string | null; ios: string | null }> {
  const r = await fetch('/api/v1/meta/app-links')
  if (!r.ok) throw new Error('Failed to load app links')
  return (await r.json()) as { android: string | null; ios: string | null }
}

export async function discoverGyms(params: DiscoverParams): Promise<GymDiscoverResponse> {
  const qs = new URLSearchParams()
  if (typeof params.latitude === 'number') qs.set('latitude', String(params.latitude))
  if (typeof params.longitude === 'number') qs.set('longitude', String(params.longitude))
  if (typeof params.radius_km === 'number') qs.set('radius_km', String(params.radius_km))
  if (params.search) qs.set('search', params.search)
  if (params.gym_type) qs.set('gym_type', params.gym_type)
  if (params.facilities?.length) params.facilities.forEach((f) => qs.append('facilities', String(f)))
  if (typeof params.min_rating === 'number') qs.set('min_rating', String(params.min_rating))
  if (typeof params.open_now === 'boolean') qs.set('open_now', String(params.open_now))
  if (params.membership_access) qs.set('membership_access', params.membership_access)
  if (params.sort_by) qs.set('sort_by', params.sort_by)
  if (typeof params.page === 'number') qs.set('page', String(params.page))
  if (typeof params.page_size === 'number') qs.set('page_size', String(params.page_size))

  const r = await fetch(`/api/v1/gyms/discover?${qs.toString()}`)
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data?.detail ?? 'Failed to load gyms')
  }
  return (await r.json()) as GymDiscoverResponse
}
