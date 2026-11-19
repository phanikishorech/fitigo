import { useResource } from '../../hooks/useResource'
import { bookingService } from '../../services/bookingService'
import { EmptyState, ErrorState, Link, Skeleton } from '../../components/common/UI'
import BookingPage from './BookingPage'

export default function EditCartVisitPage({ itemId }: { itemId: number }) {
  const resource = useResource(() => bookingService.cartItem(itemId), `cart-edit:${itemId}`)
  if (resource.loading) return <Skeleton cards={2} />
  if (resource.error) return <ErrorState message={resource.error} retry={resource.retry} />
  const item = resource.data!
  if (!item.can_edit || item.status !== 'ACTIVE') return <EmptyState title="This visit cannot be edited" description="Only unpaid cart drafts can be changed. Return to the cart to review the payment status." action={<Link to="/cart" className="fg-button fg-button--secondary">Back to cart</Link>} />
  return <BookingPage key={`${item.id}:${item.updated_at}`} gymId={item.gym_id} schedule editItem={item} />
}