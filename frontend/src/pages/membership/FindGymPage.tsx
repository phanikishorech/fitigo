import { useEffect, useState } from 'react'
import { gymService } from '../../services/gymService'
import { accessService } from '../../services/accountService'
import { getStoredLocation } from '../../screens/NearbyGyms/LocationStore'
import { useMembershipResource } from '../../hooks/useMembershipResource'
import { hasAvailableAccess } from '../../utils/membership'
import GymCard from '../../components/gym/GymCard'
import { Button, EmptyState, Heading, Link } from '../../components/common/UI'
import Icon from '../../components/common/Icon'
import { DailyAccessCard, MembershipBack, MembershipNotice, MembershipResource } from '../../components/membership/MembershipUI'

export default function FindGymPage() {
  const current = useMembershipResource(accessService.current, 'find-gym-access')
  return <div className="fm-page"><MembershipBack /><Heading title="Find a Gym" subtitle="A space for your next workout. Included in your membership." /><MembershipResource resource={current}>{calendar => hasAvailableAccess(calendar) ? <EligibleGyms /> : <div className="fm-narrow"><DailyAccessCard calendar={calendar} refresh={current.retry} /></div>}</MembershipResource></div>
}
function EligibleGyms() {
  const initial = new URLSearchParams(window.location.search)
  const [search, setSearch] = useState(initial.get('q') || '')
  const [query, setQuery] = useState(search)
  const [filter, setFilter] = useState('all'); const [page, setPage] = useState(1)
  const location = getStoredLocation()
  useEffect(() => { const timer = setTimeout(() => { setQuery(search.trim()); setPage(1) }, 350); return () => clearTimeout(timer) }, [search])
  const resource = useMembershipResource(() => gymService.discover({ search: query || undefined, membership_access: 'INCLUDED', open_now: filter === 'open' ? true : undefined, ...(filter === 'nearby' && location ? { latitude: location.latitude, longitude: location.longitude, radius_km: 10, sort_by: 'distance' } : {}), page, page_size: 12 }), `eligible-gyms:${query}:${filter}:${page}:${location?.latitude}:${location?.longitude}`)
  return <><div className="fm-search"><Icon name="search" /><input type="search" value={search} onChange={e => setSearch(e.target.value)} maxLength={120} aria-label="Search gyms or city" placeholder="Search gyms or city" />{search && <Button variant="text" onClick={() => setSearch('')} aria-label="Clear gym search"><Icon name="close" size={18} /></Button>}</div><div className="fm-filter-chips" role="group" aria-label="Filter eligible gyms">{[{ key: 'all', name: 'All gyms', icon: 'gym' as const }, { key: 'nearby', name: 'Nearby', icon: 'pin' as const }, { key: 'open', name: 'Open now', icon: 'clock' as const }].map(item => <button type="button" key={item.key} aria-pressed={filter === item.key} onClick={() => { setFilter(item.key); setPage(1) }}><Icon name={item.icon} size={17} />{item.name}</button>)}</div>{filter === 'nearby' && !location ? <MembershipNotice>Choose your location to find nearby gyms. <Link to="/location" className="fg-inline-link">Choose location</Link></MembershipNotice> : <MembershipResource resource={resource}>{data => <><div className="fm-results-heading"><p>{data.total_count} included {data.total_count === 1 ? 'gym' : 'gyms'}</p><span>1 daily access · No carry-forward</span></div>{data.gyms.length ? <div className="fg-gym-grid fm-gym-grid">{data.gyms.map(gym => <GymCard key={gym.gym_id} gym={gym} action={gym.membership_access_status === 'INCLUDED' ? <Link to={`/gyms/${gym.gym_id}/visit`} className="fg-button fg-button--primary fm-full">Visit This Gym<Icon name="arrow" size={18} /></Link> : <MembershipNotice warning>This gym is not available with your membership.</MembershipNotice>} />)}</div> : <EmptyState title="No eligible gyms available nearby" description="Try a different search or location. Only gyms marked as included by FitiGo are available for membership access." action={<Button variant="secondary" onClick={() => { setSearch(''); setFilter('all'); setPage(1) }}>Clear filters</Button>} />}<nav className="fm-pagination" aria-label="Gym results pages"><Button variant="secondary" disabled={page === 1} onClick={() => setPage(value => value - 1)}>Previous</Button><span>Page {data.page}</span><Button variant="secondary" disabled={!data.has_more} onClick={() => setPage(value => value + 1)}>Next</Button></nav></>}</MembershipResource>}<MembershipNotice>Gym inclusion is provided by FitiGo. Access availability and opening hours are validated again when gym staff scan your QR.</MembershipNotice></>
}