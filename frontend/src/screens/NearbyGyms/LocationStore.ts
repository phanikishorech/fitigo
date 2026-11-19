import type { LocationContext } from './types'
import { point } from '../../maps/geo'

const KEY = 'fitigo.location'
let active: LocationContext | null | undefined
const listeners = new Set<() => void>()
export function subscribeLocation(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } }
function emit() { listeners.forEach(listener => listener()) }

export function getStoredLocation(): LocationContext | null {
  if (active !== undefined) return active
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return active = null
    const parsed = JSON.parse(raw) as LocationContext
    if (parsed?.source === 'current' || parsed?.location_name === 'Current location') { localStorage.removeItem(KEY); return active = null }
    return active = parsed?.location_name && point(parsed.latitude, parsed.longitude) ? parsed : null
  } catch {
    return active = null
  }
}

export function setStoredLocation(loc: LocationContext) {
  if (!point(loc.latitude, loc.longitude)) return
  active = loc
  if (loc.source !== 'current' && loc.location_name !== 'Current location') {
    try { localStorage.setItem(KEY, JSON.stringify({ ...loc, source: 'manual' })) } catch { /* memory still works */ }
  }
  emit()
}

export function forgetCurrentLocation() {
  if (active?.source === 'current' || active?.location_name === 'Current location') { active = undefined; getStoredLocation(); emit() }
}

export function clearStoredLocation() {
  active = null
  try { localStorage.removeItem(KEY) } catch { /* storage may be unavailable */ }
  emit()
}
