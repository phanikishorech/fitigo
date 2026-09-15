import type { LocationContext } from './types'

const KEY = 'fitigo.location'

export function getStoredLocation(): LocationContext | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as LocationContext
    if (!parsed?.location_name) return null
    if (typeof parsed.latitude !== 'number' || typeof parsed.longitude !== 'number') return null
    return parsed
  } catch {
    return null
  }
}

export function setStoredLocation(loc: LocationContext) {
  localStorage.setItem(KEY, JSON.stringify(loc))
}

export function clearStoredLocation() {
  localStorage.removeItem(KEY)
}
