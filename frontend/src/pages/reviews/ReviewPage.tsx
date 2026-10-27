import { useState } from 'react'
import { useMutation, useResource } from '../../hooks/useResource'
import { reviewService, type BookingReview } from '../../services/accountService'
import { clearReadCache } from '../../services/readCache'
import { Alert, Button, EmptyState, ErrorState, Heading, Link, Skeleton } from '../../components/common/UI'
import Icon from '../../components/common/Icon'

export default function ReviewPage({ id }: { id: number }) {
  const result = useResource(() => reviewService.eligibility(id), `review:${id}`)
  if (result.loading) return <Skeleton cards={1} />
  if (result.error) return <ErrorState message={result.error} retry={result.retry} />
  const visit = result.data!
  if (!visit.can_review) return <div className="fg-narrow"><EmptyState title="This visit is not eligible for feedback" description={visit.reason || 'A paid individual booking and a successful check-in are required.'} action={<Link to="/bookings" className="fg-button fg-button--secondary">My bookings</Link>} />{visit.review && <section className="fg-panel"><h2>Your existing review</h2><p>{visit.review.rating} / 5 · {visit.review.status}</p><p>{visit.review.comment}</p></section>}</div>
  return <ReviewForm key={`${id}:${visit.review?.id || 'new'}`} visit={visit} />
}

function ReviewForm({ visit }: { visit: BookingReview }) {
  const [rating, setRating] = useState(visit.review?.rating || 0)
  const [comment, setComment] = useState(visit.review?.comment || '')
  const [saved, setSaved] = useState<string | null>(null)
  const mutation = useMutation()
  if (saved) return <div className="fg-narrow fg-panel fg-stack fg-center"><div className="fg-success-mark"><Icon name="check" size={36} /></div><h1>Thanks for your feedback!</h1><p>{saved === 'HIDDEN' ? 'Your changes were saved. This review remains hidden by moderation.' : 'Your gym rating has been saved. It helps others find their fit.'}</p><Link to={`/gyms/${visit.gym_id}`} className="fg-button fg-button--primary">View gym and ratings</Link><Link to="/profile/reviews" className="fg-button fg-button--secondary">My reviews</Link><Link to="/bookings">My bookings</Link></div>
  return <div className="fg-narrow"><Heading eyebrow={visit.gym_name} title={visit.review ? 'Update your gym feedback' : 'How was your gym visit?'} subtitle={`Verified individual booking #${visit.booking_id}`} /><form className="fg-panel fg-stack" onSubmit={event => {
    event.preventDefault()
    if (rating) void mutation.run(async () => {
      const review = await reviewService.submit(visit.gym_id, rating, comment, visit.booking_id)
      clearReadCache(); setSaved(review.status)
    })
  }}><fieldset disabled={mutation.pending} style={{ border: 0, padding: 0, margin: 0 }}><legend>Rate your visit</legend><div className="fg-star-input" role="group" aria-label="Rate your visit from one to five stars">{[1, 2, 3, 4, 5].map(value => <button type="button" key={value} className={value <= rating ? 'is-active' : ''} aria-label={`${value} ${value === 1 ? 'star' : 'stars'}`} aria-pressed={rating === value} onClick={() => setRating(value)}><Icon name="star" size={32} /></button>)}</div><p aria-live="polite">{rating ? `${rating} of 5 stars` : 'Choose a rating to continue'}</p><label className="fg-field">Share your feedback <small>Optional · up to 2,000 characters</small><textarea rows={5} maxLength={2000} placeholder="Tell us about the gym, equipment and your experience." value={comment} onChange={e => setComment(e.target.value)} /></label></fieldset><small className="fg-muted">One review per customer per gym. Submitting again updates that review rather than adding another rating.</small>{visit.review?.status === 'HIDDEN' && <Alert>Your existing review is hidden by moderation. Editing will not automatically publish it.</Alert>}{mutation.error && <Alert>{mutation.error}</Alert>}<Button type="submit" loading={mutation.pending} disabled={!rating}>{visit.review ? 'Save review' : 'Submit review'}</Button><Link to="/bookings">Back to My bookings</Link></form></div>
}