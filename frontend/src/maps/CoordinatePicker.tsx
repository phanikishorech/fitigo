import { useState } from 'react'
import { Button } from '../components/common/UI'
import { Input } from '../owner/UI'
import { point } from './geo'
import MapCanvas from './MapCanvas'

export default function CoordinatePicker({ latitude, longitude, onChange }: { latitude: string; longitude: string; onChange: (latitude: string, longitude: string) => void }) {
  const [show, setShow] = useState(false), current = point(latitude, longitude)
  return <div className="fg-map-picker"><div className="ow-form-grid"><Input label="Latitude" aria-label="Gym latitude" type="number" step="any" min="-90" max="90" value={latitude} onChange={event => onChange(event.target.value, longitude)} /><Input label="Longitude" aria-label="Gym longitude" type="number" step="any" min="-180" max="180" value={longitude} onChange={event => onChange(latitude, event.target.value)} /></div><p>Enter the gym’s coordinates or capture your location while at the gym. Then check the pin and click the map to correct it before saving. Existing coordinates are never replaced automatically.</p>{current ? <><Button variant="secondary" onClick={() => setShow(value => !value)}>{show ? 'Hide location map' : 'Check gym pin on map'}</Button>{show && <MapCanvas center={current} pins={[{ ...current, id: 1, title: 'Gym location — click the map to correct' }]} onPick={value => onChange(value.lat.toFixed(7), value.lng.toFixed(7))} />}</> : <p>Valid coordinates are needed for nearby discovery. Address text alone cannot place a gym on the map.</p>}</div>
}