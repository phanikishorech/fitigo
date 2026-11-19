import { useEffect, useSyncExternalStore } from 'react'
import { getStoredLocation, setStoredLocation, subscribeLocation } from '../screens/NearbyGyms/LocationStore'
import { locationSnapshot, requestPosition, subscribePosition, watchPermission } from './location'

export function useLocation(automatic = false) {
  const location = useSyncExternalStore(subscribeLocation, getStoredLocation)
  const state = useSyncExternalStore(subscribePosition, locationSnapshot)
  useEffect(() => { void watchPermission() }, [])
  useEffect(() => {
    if (!automatic) return
    const original = getStoredLocation()
    if (original) return
    void requestPosition(true).then(position => {
      if (position && getStoredLocation() === original) setStoredLocation({ location_name: 'Current location', source: 'current', latitude: position.lat, longitude: position.lng, accuracy: position.accuracy })
    })
  }, [automatic])
  async function useCurrent() {
    const original = getStoredLocation()
    const position = await requestPosition()
    if (position && getStoredLocation() === original) setStoredLocation({ location_name: 'Current location', source: 'current', latitude: position.lat, longitude: position.lng, accuracy: position.accuracy })
    return position
  }
  return { location, ...state, useCurrent }
}