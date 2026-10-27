import { useCallback, useEffect, useRef, useState } from 'react'
import { myAccessService } from '../../services/myAccessService'
import type { Membership, MembershipSummary } from '../../services/accountService'
import { useMembershipResource } from '../../hooks/useMembershipResource'
import { navigate } from '../../router'
import { Button, Skeleton } from '../common/UI'
import { MembershipPanel } from './MembershipUI'
import { MyAccessCard } from './MyAccessCard'

// Shared by My Access and Membership: read-only until the customer presses
// Generate Visit QR. Issuance, expiry and scan polling stay in the existing route.
export default function TodayMembershipAccess({ known }: { known?: { memberships: Membership[]; summary: MembershipSummary } }) {
  const initial = useRef(known)
  const resource = useMembershipResource(() => myAccessService.current(initial.current), 'today-membership-access')
  const refresh = useCallback(() => { initial.current = undefined; resource.retry() }, [resource.retry])
  const lock = useRef(false)
  const [generating, setGenerating] = useState(false)
  useEffect(() => {
    const visible = () => { if (!document.hidden) refresh() }
    window.addEventListener('focus', visible); document.addEventListener('visibilitychange', visible)
    return () => { window.removeEventListener('focus', visible); document.removeEventListener('visibilitychange', visible) }
  }, [refresh])
  if (resource.loading) return <Skeleton cards={1} />
  if (resource.error || !resource.data) return <MembershipPanel><h2>Unable to load access status.</h2><p role="alert">{resource.error || 'Please try again.'}</p><Button onClick={refresh}>Retry</Button></MembershipPanel>
  return <MyAccessCard data={resource.data} refresh={refresh} generating={generating} generate={() => {
    if (lock.current) return
    lock.current = true; setGenerating(true)
    navigate('/access/qr?generate=1')
  }} />
}