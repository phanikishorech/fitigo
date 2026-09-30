import { useState } from 'react'
import { useMutation, useResource } from '../../hooks/useResource'
import { bookingService } from '../../services/bookingService'
import { reviewService } from '../../services/accountService'
import { canReview } from '../../utils/booking'
import { Alert, Button, EmptyState, ErrorState, Heading, Link, Skeleton } from '../../components/common/UI'
import Icon from '../../components/common/Icon'

export default function ReviewPage({ id }: { id: number }) {
  const result = useResource(() => bookingService.visits('past'), String(id))
  const [rating, setRating] = useState(0)
  const [comment, setComment] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const mutation = useMutation()
  if (result.loading) return <Skeleton cards={1} />
  if (result.error) return <ErrorState message={result.error} retry={result.retry} />
  const visit = result.data?.find(item => item.booking_id === id)
  if (!visit || !canReview(visit)) return <EmptyState title="This visit is not eligible for a review" description="Reviews are available after your booking attendance is verified by the gym." action={<Link to="/profile/visits" className="fg-button fg-button--secondary">View visits</Link>} />
  if (submitted) return <div className="fg-narrow fg-panel fg-stack fg-center"><div className="fg-success-mark"><Icon name="check" size={36} /></div><h1>Thanks for your feedback!</h1><p className="fg-muted">Your review helps others find their fit.</p><h2>What would you like to do next?</h2><Link to={`/gyms/${visit.gym_id}`} className="fg-button fg-button--primary">Book again</Link><Link to="/bookings" className="fg-button fg-button--secondary">View upcoming visits</Link><Link to="/explore" className="fg-inline-link">Browse gyms</Link><Link to="/profile/membership" className="fg-inline-link">Manage membership</Link></div>
  return <div className="fg-narrow"><Heading eyebrow={visit.gym_name} title="How was your experience?" subtitle="A little feedback goes a long way." /><form className="fg-panel fg-stack" onSubmit={e => { e.preventDefault(); if (rating) void mutation.run(async () => { await reviewService.submit(visit.gym_id, rating, comment); setSubmitted(true) }) }}><div className="fg-star-input" role="group" aria-label="Rate your visit from one to five stars">{[1, 2, 3, 4, 5].map(value => <button type="button" key={value} className={value <= rating ? 'is-active' : ''} aria-label={`${value} ${value === 1 ? 'star' : 'stars'}`} aria-pressed={rating === value} onClick={() => setRating(value)}><Icon name="star" size={32} /></button>)}</div><label className="fg-field">Share your feedback <small>Optional · up to 2,000 characters</small><textarea rows={5} maxLength={2000} placeholder="What did you love? What could be better?" value={comment} onChange={e => setComment(e.target.value)} /></label><small className="fg-muted">The gym service stores one review per customer per gym. Submitting again updates your existing gym review.</small>{mutation.error && <Alert>{mutation.error}</Alert>}<Button type="submit" loading={mutation.pending} disabled={!rating}>Submit review</Button></form></div>
}