import type { DiscoverParams } from '../screens/NearbyGyms/api'
import type { GymDiscoverResponse, GymFacility, LocationContext } from '../screens/NearbyGyms/types'
import type { GymDetailsResponse } from '../screens/GymDetails/types'
import { request } from './client'
import { cachedRead, clearReadCache } from './readCache'
import { subscribeAuth } from '../auth'

subscribeAuth(clearReadCache)

export function discoveryQuery(params: DiscoverParams) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '' && value !== null) {
      if (Array.isArray(value)) value.forEach(item => query.append(key, String(item)))
      else query.set(key, String(value))
    }
  })
  return query.toString()
}
export const gymService = {
  discover: (params: DiscoverParams) => request<GymDiscoverResponse>(`/gyms/discover?${discoveryQuery(params)}`),
  details: (id: number) => cachedRead(`gym:${id}`, () => request<GymDetailsResponse>(`/gyms/${id}/details`)),
  types: () => cachedRead('gym-types', () => request<string[]>('/meta/gym-types'), 300000),
  facilities: () => cachedRead('facilities', () => request<GymFacility[]>('/facilities'), 300000),
  locations: (search = '') => request<(LocationContext & { gym_count: number })[]>(`/meta/locations?limit=40&search=${encodeURIComponent(search)}`)
}
// Deliberately not mapped to /profile/favorites: that endpoint means frequent visits.
export const favoritesService = { supported: false, explanation: 'Saving gyms is not available yet. You can bookmark a gym page in your browser.' }