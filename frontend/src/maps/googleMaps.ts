import type { Point, TravelMode } from './geo'

// Narrow interfaces for the official browser API, not a framework wrapper.
export interface Listener { remove(): void }
export interface Bounds { extend(point: Point): Bounds }
export interface MapInstance {
  fitBounds(bounds: Bounds, padding?: number): void
  setCenter(point: Point): void
  setZoom(zoom: number): void
  getZoom(): number | undefined
  addListener(event: string, callback: (event: MapEvent) => void): Listener
}
export interface MapEvent { latLng?: { lat(): number; lng(): number } }
export interface Overlay { setMap(map: MapInstance | null): void }
export interface Marker {
  map: MapInstance | null
  addListener(event: string, callback: (event: MapEvent) => void): Listener
}
export interface RouteResult {
  distanceMeters?: number
  durationMillis?: number
  viewport?: Bounds
  warnings?: string[]
  createPolylines(): Overlay[]
}
export interface MapsApi {
  importLibrary(name: string): Promise<unknown>
  Map: new (element: HTMLElement, options: Record<string, unknown>) => MapInstance
  LatLngBounds: new () => Bounds
  Circle: new (options: Record<string, unknown>) => Overlay
  marker: { AdvancedMarkerElement: new (options: Record<string, unknown>) => Marker }
  routes: { Route: { computeRoutes(request: { origin: Point; destination: Point; travelMode: TravelMode; fields: string[] }): Promise<{ routes?: RouteResult[] }> } }
}
declare global {
  interface Window { google?: { maps: MapsApi }; fitigoMapsReady?: () => void; gm_authFailure?: () => void }
}
const env = (import.meta as ImportMeta & { env: Record<string, string | undefined> }).env
export const mapId = env.VITE_GOOGLE_MAPS_MAP_ID
let loading: Promise<MapsApi> | null = null
let authFailed = false
const failures = new Set<() => void>()
export function onMapFailure(callback: () => void) { failures.add(callback); return () => { failures.delete(callback) } }
export function loadMaps(): Promise<MapsApi> {
  if (authFailed) return Promise.reject(new Error('Google Maps authorization failed. Please use the gym list or Open in Google Maps.'))
  if (window.google?.maps?.Map && window.google.maps.marker) return Promise.resolve(window.google.maps)
  if (loading) return loading
  if (!env.VITE_GOOGLE_MAPS_API_KEY || !mapId) return Promise.reject(new Error('Interactive maps are not configured yet. You can still browse gyms and open directions in Google Maps.'))
  loading = new Promise<MapsApi>((resolve, reject) => {
    const script = document.createElement('script')
    const fail = (message: string) => { clearTimeout(timer); script.remove(); loading = null; reject(new Error(message)) }
    const timer = window.setTimeout(() => fail('Google Maps took too long to load. Check your connection and retry.'), 20000)
    window.gm_authFailure = () => { authFailed = true; failures.forEach(callback => callback()); fail('Google Maps authorization failed. Please use the gym list or Open in Google Maps.') }
    window.fitigoMapsReady = () => {
      const maps = window.google?.maps
      if (!maps) { fail('Google Maps could not load. Please retry.'); return }
      Promise.all([maps.importLibrary('maps'), maps.importLibrary('marker')]).then(() => { clearTimeout(timer); resolve(maps) }).catch(() => fail('Google Maps could not load. Please retry.'))
    }
    const query = new URLSearchParams({ key: env.VITE_GOOGLE_MAPS_API_KEY!, v: 'quarterly', loading: 'async', callback: 'fitigoMapsReady' })
    script.src = `https://maps.googleapis.com/maps/api/js?${query}`
    script.async = true
    script.nonce = document.querySelector<HTMLScriptElement>('script[nonce]')?.nonce || ''
    script.onerror = () => fail('Google Maps could not load. Check your connection and retry.')
    document.head.append(script)
  })
  return loading
}