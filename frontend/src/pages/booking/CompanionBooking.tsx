import { useEffect } from 'react'
import { visitAccessService } from '../../services/visitAccessService'
import { navigate } from '../../router'
import { todayFrom } from '../../utils/membership'
import { useMembershipResource } from '../../hooks/useMembershipResource'
import { Button } from '../../components/common/UI'
import { MembershipPanel, MembershipResource } from '../../components/membership/MembershipUI'
import BookingPage from './BookingPage'

// Eligibility boundary only. All people count, scheduling, cart and checkout UI
// stays in the existing booking implementation, not a parallel booking system.
export default function CompanionBooking({ gymId }: { gymId: number }) {
  const resource = useMembershipResource(() => visitAccessService.check(gymId), `companions:${gymId}`)
  useEffect(() => {
    if (resource.data && resource.data.decision !== 'MEMBERSHIP') navigate(`/gyms/${gymId}/book/access`)
  }, [gymId, resource.data])
  if (resource.error) return <MembershipPanel><p role="alert">Unable to check your membership access.</p><Button onClick={resource.retry}>Try Again</Button></MembershipPanel>
  return <MembershipResource resource={resource}>{result => {
    if (result.decision !== 'MEMBERSHIP') return <p role="status">Opening visit options…</p>
    return <BookingPage gymId={gymId} schedule companionsDate={todayFrom(result.calendar)!.date} />
  }}</MembershipResource>
}