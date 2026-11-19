import { useState } from 'react'
import type { GymDiscoverItem } from '../screens/NearbyGyms/types'
import { Image, Link } from '../components/common/UI'
import { money } from '../services/client'
import MapCanvas from './MapCanvas'
import { point, type Point } from './geo'
import type { UserPosition } from './location'

export default function DiscoveryMap({ gyms, center, user, radius }: { gyms: GymDiscoverItem[]; center: Point; user: UserPosition | null; radius: number }) {
  const [selected, setSelected] = useState<number | null>(null)
  const gym = gyms.find(item => item.gym_id === selected)
  const pins = gyms.flatMap(item => { const position = point(item.latitude, item.longitude); return position ? [{ ...position, id: item.gym_id, title: item.gym_name }] : [] })
  return <div className="fg-map-layout"><MapCanvas center={center} pins={pins} user={user} radius={radius} onSelect={setSelected} /><aside className="fg-panel fg-stack" aria-live="polite">{gym ? <div className="fg-map-preview"><Image src={gym.primary_image} alt={gym.gym_name} /><div className="fg-stack"><h3>{gym.gym_name}</h3><p>{gym.address || gym.locality || gym.city}</p>{gym.distance_km != null && <p>{gym.distance_km.toFixed(1)} km from selected location</p>}{gym.average_rating != null && <p>{gym.average_rating.toFixed(1)} / 5 · {gym.review_count} reviews</p>}{gym.starting_price != null && <p>From {money(gym.starting_price)} / visit</p>}<Link to={`/gyms/${gym.gym_id}`} className="fg-button fg-button--primary">View Gym Details</Link></div></div> : <><h3>{gyms.length ? 'Find your next workout' : 'No FitiGo gyms nearby'}</h3><p>{gyms.length ? 'Select a green marker to preview a FitiGo partner gym. Numbered markers expand when selected.' : `No partner gyms match your filters within ${radius} km. Try a wider radius or another area.`}</p></>}{user && <small>Blue marker: your location · accuracy approximately {Math.round(user.accuracy)} m</small>}<small>The map shows this results page. Use Previous / Next to explore more. Panning does not change your selected area.</small></aside></div>
}