import { membershipService } from '../../services/accountService'
import { useMembershipResource } from '../../hooks/useMembershipResource'
import { MembershipBack, MembershipPanel, MembershipResource, NoMembership } from '../../components/membership/MembershipUI'
import { MembershipPause } from '../../components/membership/MembershipPause'
import { Heading } from '../../components/common/UI'

export default function MembershipPausePage() {
  const resource = useMembershipResource(membershipService.mine, 'pause-memberships')
  return <div className="fm-page fm-narrow"><MembershipBack /><Heading title="Pause Membership" subtitle="Review the current pause policy for your membership." /><MembershipResource resource={resource}>{items => !items.length ? <NoMembership /> : <div className="fm-stack">{items.map(item => <MembershipPanel key={item.id} title={item.terms_snapshot?.name || `Membership #${item.id}`}><MembershipPause membershipId={item.id} onChanged={resource.retry} /></MembershipPanel>)}</div>}</MembershipResource></div>
}