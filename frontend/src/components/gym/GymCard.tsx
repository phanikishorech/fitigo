import type { GymDiscoverItem } from '../../screens/NearbyGyms/types'
import type { ReactNode } from 'react'
import Icon from '../common/Icon'
import { Badge, Image, Link } from '../common/UI'

export default function GymCard({ gym, action }: { gym: GymDiscoverItem; action?: ReactNode }) {
  return <article className="fg-gym-card"><div className="fg-gym-photo"><Link to={`/gyms/${gym.gym_id}`} label={`View ${gym.gym_name}`}><Image src={gym.primary_image} alt={gym.gym_name} /></Link>{gym.is_featured && <Badge>FITIGO SELECT</Badge>}</div>
    <div className="fg-gym-body"><div className="fg-row"><span className="fg-rating"><Icon name="star" size={15} />{gym.average_rating != null ? gym.average_rating.toFixed(1) : 'New'}{gym.review_count > 0 && <small>({gym.review_count})</small>}</span>{gym.is_open_now != null && <span className={gym.is_open_now ? 'fg-open' : 'fg-muted'}>{gym.is_open_now ? 'Open now' : 'Closed now'}</span>}</div><h3><Link to={`/gyms/${gym.gym_id}`}>{gym.gym_name}</Link></h3><p className="fg-card-location"><Icon name="pin" size={15} />{[gym.locality, gym.city].filter(Boolean).join(', ') || 'View location'}{gym.distance_km != null && <span> · {gym.distance_km.toFixed(1)} km</span>}</p><div className="fg-facility-tags">{gym.facilities.slice(0, 3).map(f => <span key={f.id}>{f.name}</span>)}</div><div className="fg-card-bottom"><span>{gym.membership_access_status === 'INCLUDED' ? 'Included in your plan' : 'Find your perfect fit'}</span><Link to={`/gyms/${gym.gym_id}`} className="fg-inline-link">View gym <Icon name="arrow" size={16} /></Link></div></div>
    {action && <div className="fm-gym-card-action">{action}</div>}
  </article>
}