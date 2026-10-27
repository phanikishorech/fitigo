import { useState } from 'react'
import { useResource } from '../../hooks/useResource'
import { bookingService, type Visit } from '../../services/bookingService'
import { dateLabel, money, localDate } from '../../services/client'
import { canReview } from '../../utils/booking'
import { Badge, EmptyState, ErrorState, Heading, Link, Skeleton } from '../../components/common/UI'
import Icon from '../../components/common/Icon'

export function VisitCard({ visit }: { visit: Visit }) {
  const attended = visit.booking_status === 'COMPLETED'
  return <article className="fg-panel fg-stack"><div className="fg-row"><h3>{visit.gym_name}</h3><Badge tone={attended || visit.booking_status === 'CONFIRMED' ? 'success' : 'neutral'}>{attended ? 'Attended' : visit.booking_status.replaceAll('_', ' ').toLowerCase()}</Badge></div><p className="fg-muted">{visit.class_name || visit.access_type.replaceAll('_', ' ')}</p><div className="fg-row"><p><Icon name="calendar" size={16} /> {dateLabel(visit.visit_date)} · {visit.start_time.slice(0, 5)} IST</p><strong>{visit.membership_covered ? 'Membership access' : visit.amount_paid != null ? money(visit.amount_paid, visit.currency) : ''}</strong></div>{visit.booking_access?.qr_available && <Link to={`/bookings/${visit.booking_id}`} className="fg-button fg-button--primary">Show Booking QR</Link>}{visit.booking_access?.can_set_visitors && <Link to={`/bookings/${visit.booking_id}`} className="fg-inline-link">Add visitor details for QR</Link>}<div className="fg-row">{visit.booking_id > 0 ? <Link to={`/bookings/${visit.booking_id}`} className="fg-inline-link">View details <Icon name="arrow" size={16} /></Link> : <Link to={`/gyms/${visit.gym_id}`} className="fg-inline-link">View gym</Link>}{visit.review_rating != null && <span aria-label={`Your rating: ${visit.review_rating} out of 5`}>Your rating: {visit.review_rating}/5{visit.review_status === 'HIDDEN' ? ' (hidden by moderation)' : ''}</span>}{canReview(visit) ? <Link to={`/reviews/${visit.booking_id}`} className="fg-inline-link">{visit.review_id ? 'Edit review' : 'Rate visit'}</Link> : attended ? <Link to={`/gyms/${visit.gym_id}`} className="fg-inline-link">Book again</Link> : null}</div></article>
}
export default function BookingsPage({ history = false, checkins = false, reviews = false }: { history?: boolean; checkins?: boolean; reviews?: boolean }) {
  const [tab, setTab] = useState('all')
  const result = useResource(() => bookingService.visits('all'), 'visits')
  const seenReviewGyms = new Set<number>()
  const items = (result.data ?? []).filter(visit => {
    if (visit.membership_covered || visit.booking_id <= 0) return false
    if (reviews) {
      if (!(canReview(visit) || !!visit.review_id) || seenReviewGyms.has(visit.gym_id)) return false
      // Prefer a qualifying visit so an existing gym review stays editable.
      if (!canReview(visit) && result.data?.some(other => other.gym_id === visit.gym_id && canReview(other))) return false
      seenReviewGyms.add(visit.gym_id)
      return true
    }
    if (tab === 'all') return true
    if (checkins) return visit.attendance_status === 'ATTENDED'
    const upcoming = visit.booking_status === 'CONFIRMED' && !visit.attendance_status && visit.visit_date >= localDate()
    return tab === 'upcoming' ? upcoming : !upcoming
  }).sort((a, b) => tab === 'upcoming' ? a.visit_date.localeCompare(b.visit_date) : b.visit_date.localeCompare(a.visit_date))
  return <><Heading eyebrow="MAKE MOVEMENT A HABIT" title={reviews ? 'Your reviews' : checkins ? 'Check-in history' : history ? 'Your visits' : 'My bookings'} subtitle={reviews ? 'Your gym ratings and feedback after verified individual visits.' : 'Individual bookings only. Rate your gym after a successful check-in.'} />{!reviews && !checkins && <div className="fg-tabs">{['all', 'upcoming', 'history'].map(value => <button key={value} className={tab === value ? 'is-active' : ''} aria-pressed={tab === value} onClick={() => setTab(value)}>{value === 'all' ? 'All bookings' : value === 'upcoming' ? 'Upcoming' : 'History'}</button>)}</div>}{result.loading ? <Skeleton cards={2} /> : result.error ? <ErrorState message={result.error} retry={result.retry} /> : !items.length ? <EmptyState title={reviews ? 'No eligible visits to review' : tab === 'upcoming' ? 'No upcoming visits' : 'No visits yet'} description={reviews ? 'You can review a gym after attendance has been verified.' : 'Every routine starts with a first visit. Let’s find yours.'} action={<Link to="/explore" className="fg-button fg-button--primary">Explore gyms</Link>} /> : <div className="fg-two-column">{items.map(visit => <VisitCard key={visit.booking_id} visit={visit} />)}</div>}</>
}