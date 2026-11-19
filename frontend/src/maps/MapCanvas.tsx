import { useEffect, useRef, useState } from 'react'
import { ErrorState } from '../components/common/UI'
import { clusterPoints, type Point, type TravelMode } from './geo'
import { loadMaps, mapId, onMapFailure, type MapInstance, type MapsApi, type Marker, type Overlay, type RouteResult } from './googleMaps'
import type { UserPosition } from './location'
import './maps.css'

export type MapPin = Point & { id: number; title: string }
export type RouteRequest = { origin: Point; destination: Point; mode: TravelMode; version: number }
type Props = { center: Point; pins: MapPin[]; user?: UserPosition | null; radius?: number; onSelect?: (id: number) => void; onPick?: (point: Point) => void; route?: RouteRequest | null; onRoute?: (result: RouteResult | null, error: string) => void }

export default function MapCanvas(props: Props) {
  const element = useRef<HTMLDivElement>(null), latest = useRef(props)
  latest.current = props
  const [ready, setReady] = useState<{ map: MapInstance; api: MapsApi } | null>(null)
  const [error, setError] = useState(''), [attempt, setAttempt] = useState(0), [zoom, setZoom] = useState(13)
  useEffect(() => {
    let alive = true
    let listeners: { remove(): void }[] = []
    setError('')
    const off = onMapFailure(() => { if (alive) setError('Google Maps authorization failed. Use the list or open directions in Google Maps.') })
    void loadMaps().then(api => {
      if (!alive || !element.current) return
      const map = new api.Map(element.current, { center: latest.current.center, zoom: 13, mapId, gestureHandling: 'cooperative', mapTypeControl: false, streetViewControl: false, fullscreenControl: true, zoomControl: true, clickableIcons: false })
      listeners = [map.addListener('zoom_changed', () => setZoom(map.getZoom() ?? 13)), map.addListener('click', event => {
        if (event.latLng) latest.current.onPick?.({ lat: event.latLng.lat(), lng: event.latLng.lng() })
      })]
      setReady({ map, api })
    }).catch(reason => { if (alive) setError(reason.message) })
    return () => { alive = false; off(); listeners.forEach(listener => listener.remove()); setReady(null) }
  }, [attempt])
  const pinsKey = JSON.stringify(props.pins)
  useEffect(() => {
    if (!ready) return
    const { map, api } = ready, pins = latest.current.pins
    const bounds = new api.LatLngBounds().extend(latest.current.center)
    pins.forEach(pin => bounds.extend(pin))
    if (pins.length) map.fitBounds(bounds, 60)
    else { map.setCenter(latest.current.center); map.setZoom(props.radius ? Math.max(8, 14 - Math.log2(props.radius / 5)) : 15) }
    const clamp = map.addListener('idle', () => { if ((map.getZoom() ?? 0) > 16) map.setZoom(16); clamp.remove() })
    return () => clamp.remove()
  }, [ready, pinsKey, props.center.lat, props.center.lng, props.radius])
  useEffect(() => {
    if (!ready) return
    const { api, map } = ready
    const markers: Marker[] = [], listeners: { remove(): void }[] = []
    for (const group of clusterPoints(latest.current.pins, zoom)) {
      const pin = group[0], content = document.createElement('div')
      content.className = 'fg-map-pin'; content.textContent = group.length > 1 ? String(group.length) : 'F'
      const marker = new api.marker.AdvancedMarkerElement({ map, position: { lat: pin.lat, lng: pin.lng }, title: group.length > 1 ? `${group.length} FitiGo gyms — zoom in` : pin.title, content })
      listeners.push(marker.addListener('click', () => {
        if (group.length > 1) { map.setCenter(pin); map.setZoom(Math.min(19, zoom + 2)) }
        else latest.current.onSelect?.(pin.id)
      }))
      markers.push(marker)
    }
    return () => { listeners.forEach(listener => listener.remove()); markers.forEach(marker => { marker.map = null }) }
  }, [ready, pinsKey, zoom])
  useEffect(() => {
    if (!ready || !props.user) return
    const { api, map } = ready, content = document.createElement('div')
    content.className = 'fg-map-pin fg-map-pin--current'
    const marker = new api.marker.AdvancedMarkerElement({ map, position: { lat: props.user.lat, lng: props.user.lng }, title: 'Your current location', content, zIndex: 1000 })
    const circle = new api.Circle({ map, center: props.user, radius: props.user.accuracy, fillColor: '#2563eb', fillOpacity: 0.08, strokeColor: '#2563eb', strokeOpacity: 0.35, strokeWeight: 1, clickable: false })
    return () => { marker.map = null; circle.setMap(null) }
  }, [ready, props.user?.lat, props.user?.lng, props.user?.accuracy])
  const routeKey = JSON.stringify(props.route)
  useEffect(() => {
    if (!props.route) return
    if (error) { latest.current.onRoute?.(null, 'Map preview unavailable. Open Google Maps for directions.'); return }
    if (!ready) return
    let alive = true, lines: Overlay[] = []
    const { api, map } = ready, request = props.route
    latest.current.onRoute?.(null, '')
    void api.importLibrary('routes').then(() => api.routes.Route.computeRoutes({ origin: request.origin, destination: request.destination, travelMode: request.mode, fields: ['path', 'viewport', 'distanceMeters', 'durationMillis', 'warnings'] })).then(result => {
      if (!alive) return
      const route = result.routes?.[0]
      if (!route) throw new Error('No route')
      lines = route.createPolylines(); lines.forEach(line => line.setMap(map))
      if (route.viewport) map.fitBounds(route.viewport, 45)
      latest.current.onRoute?.(route, '')
    }).catch(() => { if (alive) latest.current.onRoute?.(null, 'No route preview is available for this travel mode. Try another mode or open Google Maps.') })
    return () => { alive = false; lines.forEach(line => line.setMap(null)) }
  }, [ready, routeKey, error])
  return <div>{!ready && !error && <p role="status" className="fg-map-status">Loading Google Maps…</p>}{error && <ErrorState message={error} retry={() => setAttempt(value => value + 1)} />}<div ref={element} className="fg-map-surface" aria-label="Interactive Google Map" hidden={!!error} /></div>
}