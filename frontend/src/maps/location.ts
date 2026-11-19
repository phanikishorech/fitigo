import { forgetCurrentLocation } from '../screens/NearbyGyms/LocationStore'
import type { Point } from './geo'

export type UserPosition = Point & { accuracy: number; timestamp: number }
type State = { position: UserPosition | null; busy: boolean; error: string; denied: boolean }
let state: State = { position: null, busy: false, error: '', denied: false }
let pending: Promise<UserPosition | null> | null = null
let attempted = false, permission: PermissionStatus | null = null, watching = false, generation = 0
const listeners = new Set<() => void>()
export function subscribePosition(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } }
export function locationSnapshot() { return state }
function update(patch: Partial<State>) { state = { ...state, ...patch }; listeners.forEach(listener => listener()) }
export async function watchPermission() {
  if (watching || !navigator.permissions) return
  watching = true
  try {
    permission = await navigator.permissions.query({ name: 'geolocation' })
    const change = () => {
      if (permission?.state !== 'granted') {
        generation++
        update({ position: null, busy: false, denied: permission?.state === 'denied', error: permission?.state === 'denied' ? 'Location permission is denied. Choose an area or allow location in your browser settings.' : '' })
        forgetCurrentLocation()
      } else update({ denied: false, error: '' })
    }
    permission.addEventListener('change', change)
    if (permission.state === 'denied') change()
  } catch { /* Permission queries are not available in every browser. */ }
}
export function requestPosition(automatic = false): Promise<UserPosition | null> {
  if (pending) return pending
  if (state.position && Date.now() - state.position.timestamp < 300000) return Promise.resolve(state.position)
  if (automatic && attempted) return Promise.resolve(null)
  attempted = true
  pending = (async () => {
    await watchPermission()
    if (state.denied) return null
    if (!navigator.geolocation || !window.isSecureContext) {
      update({ position: null, error: 'Location requires a supported browser and HTTPS. Please choose an area.' }); return null
    }
    update({ busy: true, error: '' })
    const version = generation
    return new Promise<UserPosition | null>(resolve => {
      navigator.geolocation.getCurrentPosition(result => {
        if (version !== generation) { resolve(null); return }
        const position = { lat: result.coords.latitude, lng: result.coords.longitude, accuracy: result.coords.accuracy, timestamp: result.timestamp }
        update({ position, busy: false, denied: false }); resolve(position)
      }, error => {
        if (version !== generation) { resolve(null); return }
        const message = error.code === 1 ? 'Location permission denied. Choose an area or allow location in your browser settings.' : error.code === 3 ? 'Location request timed out. Try again or choose an area.' : 'Your location is unavailable. Try again or choose an area.'
        update({ position: null, busy: false, error: message, denied: error.code === 1 }); forgetCurrentLocation(); resolve(null)
      }, { timeout: 12000, maximumAge: 300000, enableHighAccuracy: false })
    })
  })().finally(() => { pending = null })
  return pending
}