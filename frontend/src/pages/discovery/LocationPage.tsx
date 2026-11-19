import { useState } from 'react'
import { useResource } from '../../hooks/useResource'
import { gymService } from '../../services/gymService'
import { setStoredLocation, getStoredLocation } from '../../screens/NearbyGyms/LocationStore'
import type { LocationContext } from '../../screens/NearbyGyms/types'
import { useDebouncedValue } from '../../screens/NearbyGyms/useDebouncedValue'
import { navigate } from '../../router'
import { Alert, Button, EmptyState, ErrorState, Heading, Skeleton } from '../../components/common/UI'
import Icon from '../../components/common/Icon'
import { useLocation } from '../../maps/useLocation'

export default function LocationPage() {
  const [search, setSearch] = useState('')
  const query = useDebouncedValue(search, 300)
  const locations = useResource(() => gymService.locations(query), query)
  const geo = useLocation()
  const busy = geo.busy
  const [error, setError] = useState('')
  const select = (location: LocationContext) => { try { setStoredLocation(location); navigate('/explore') } catch { setError('Your browser could not save this location. Please enable site storage and try again.') } }
  const current = async () => { const position = await geo.useCurrent(); if (position) navigate('/explore') }
  return <div className="fg-narrow"><Heading eyebrow="LET’S GET YOU MOVING" title="Where do you want to work out?" subtitle="Find great workout spaces around your neighbourhood." /><div className="fg-panel fg-stack"><label className="fg-search"><Icon name="search" /><input autoFocus placeholder="Search city or area" aria-label="Search city or area" value={search} onChange={e => setSearch(e.target.value)} /></label><Button variant="secondary" loading={busy} onClick={current}><Icon name="pin" />Use current location</Button>{(error || geo.error) && <Alert>{error || geo.error}</Alert>}{getStoredLocation() && <Button variant="text" onClick={() => select(getStoredLocation()!)}>Use {getStoredLocation()!.location_name}</Button>}<h2>Explore an area</h2>{locations.loading ? <Skeleton cards={1} /> : locations.error ? <ErrorState message={locations.error} retry={locations.retry} /> : !locations.data?.length ? <EmptyState title="No areas found" description="Try a nearby city or a different spelling." /> : locations.data.map(location => <button className="fg-list-row" key={`${location.location_name}-${location.city}`} onClick={() => select(location)}><Icon name="pin" /><span><strong>{location.location_name}</strong><small>{[location.city, location.state].filter(Boolean).join(', ')} · {location.gym_count} gyms</small></span><Icon name="chevron" /></button>)}</div></div>
}