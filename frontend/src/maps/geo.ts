export type Point = { lat: number; lng: number }
export type TravelMode = 'DRIVING' | 'WALKING' | 'BICYCLING' | 'TRANSIT'
export function point(latitude: unknown, longitude: unknown): Point | null {
  if (latitude == null || longitude == null || String(latitude).trim() === '' || String(longitude).trim() === '') return null
  const lat = Number(latitude), lng = Number(longitude)
  return Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180 ? { lat, lng } : null
}
export function directionsUrl(destination: Point, mode: TravelMode, origin?: Point | null) {
  const query = new URLSearchParams({ api: '1', destination: `${destination.lat},${destination.lng}`, travelmode: mode.toLowerCase() })
  if (origin) query.set('origin', `${origin.lat},${origin.lng}`)
  return `https://www.google.com/maps/dir/?${query}`
}
// Zoom-dependent Web Mercator grid, bounded to the current API page.
export function clusterPoints<T extends Point>(points: T[], zoom: number): T[][] {
  if (zoom >= 19) return points.map(item => [item])
  const scale = 256 * 2 ** zoom, cells = new Map<string, T[]>()
  for (const item of points) {
    const sine = Math.sin(Math.max(-85, Math.min(85, item.lat)) * Math.PI / 180)
    const x = (item.lng + 180) / 360 * scale
    const y = (0.5 - Math.log((1 + sine) / (1 - sine)) / (4 * Math.PI)) * scale
    const key = `${Math.floor(x / 64)}:${Math.floor(y / 64)}`
    cells.set(key, [...(cells.get(key) ?? []), item])
  }
  return [...cells.values()]
}