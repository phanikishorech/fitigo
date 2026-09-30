import { useState } from 'react'
import { useResource } from '../../hooks/useResource'
import { bookingService, type Visit } from '../../services/bookingService'
import { dateLabel, money } from '../../services/client'
import { canReview } from '../../utils/booking'
import { Badge, EmptyState, ErrorState, Heading, Link, Skeleton } from '../../components/common/UI'
import Icon from '../../components/common/Icon'

export function VisitCard({ visit }: { visit: Visit }) {
  const attended = visit.attendance_status === 'ATTENDED'
  return <article className="fg-panel fg-stack"><div className="fg-row"><h3>{visit.gym_name}</h3><Badge tone={attended || visit.booking_status === 'CONFIRMED' ? 'success' : 'neutral'}>{attended ? 'Attended' : visit.booking_status.replaceAll('_', ' ').toLowerCase()}</Badge></div><p className="fg-muted">{visit.class_name || visit.access_type.replaceAll('_', ' ')}</p><div className="fg-row"><p><Icon name="calendar" size={16} /> {dateLabel(visit.visit_date)} · {visit.start_time.slice(0, 5)}</p><strong>{visit.membership_covered ? 'Membership access' : visit.amount_paid != null ? money(visit.amount_paid, visit.currency) : ''}</strong></div><div className="fg-row">{visit.booking_id > 0 ? <Link to={`/bookings/${visit.booking_id}`} className="fg-inline-link">View details <Icon name="arrow" size={16} /></Link> : <Link to={`/gyms/${visit.gym_id}`} className="fg-inline-link">View gym</Link>}{canReview(visit) ? <Link to={`/reviews/${visit.booking_id}`} className="fg-inline-link">Rate visit</Link> : attended ? <Link to={`/gyms/${visit.gym_id}`} className="fg-inline-link">Book again</Link> : null}</div></article>
}
export default function BookingsPage({ history = false, checkins = false, reviews = false }: { history?: boolean; checkins?: boolean; reviews?: boolean }) {
  const [tab, setTab] = useState(history || reviews || checkins ? 'history' : 'upcoming')
  const result = useResource(() => bookingService.visits('all'), 'visits')
  const items = (result.data ?? []).filter(visit => {
    if (reviews) return canReview(visit)
    if (checkins) return visit.attendance_status === 'ATTENDED'
    const upcoming = visit.booking_status === 'CONFIRMED' && !visit.attendance_status && visit.visit_date >= new Date().toISOString().slice(0, 10)
    return tab === 'upcoming' ? upcoming : !upcoming
  }).sort((a, b) => tab === 'upcoming' ? a.visit_date.localeCompare(b.visit_date) : b.visit_date.localeCompare(a.visit_date))
  return <><Heading eyebrow="MAKE MOVEMENT A HABIT" title={reviews ? 'Your reviews' : checkins ? 'Check-in history' : history ? 'Your visits' : 'Your bookings'} subtitle={reviews ? 'Share feedback on your verified gym visits.' : 'Your next workout and the ones that got you here.'} />{!reviews && !checkins && <div className="fg-tabs">{['upcoming', 'history'].map(value => <button key={value} className={tab === value ? 'is-active' : ''} aria-pressed={tab === value} onClick={() => setTab(value)}>{value === 'upcoming' ? 'Upcoming' : 'History'}</button>)}</div>}{result.loading ? <Skeleton cards={2} /> : result.error ? <ErrorState message={result.error} retry={result.retry} /> : !items.length ? <EmptyState title={reviews ? 'No eligible visits to review' : tab === 'upcoming' ? 'No upcoming visits' : 'No visits yet'} description={reviews ? 'You can review a gym after attendance has been verified.' : 'Every routine starts with a first visit. Let’s find yours.'} action={<Link to="/explore" className="fg-button fg-button--primary">Explore gyms</Link>} /> : <div className="fg-two-column">{items.map(visit => <VisitCard key={visit.booking_id} visit={visit} />)}</div>}</>
}