import { useResource } from '../../hooks/useResource'
import { request } from '../../services/client'

export default function AccountDeliveryNotice() {
  const resource = useResource(() => request<{ email_available: boolean; mobile_available: boolean }>('/auth/otp/options', { cache: 'no-store' }), 'account-delivery-options')
  return <p className="fg-muted">{resource.loading ? 'Checking account message availability…' : resource.error ? 'Account message availability could not be verified. No delivery is promised.' : `Account sign-in codes: email ${resource.data?.email_available ? 'configured' : 'unavailable'}, SMS ${resource.data?.mobile_available ? 'configured' : 'unavailable'}. Provider configuration does not guarantee delivery.`} Saving contact details does not verify ownership.</p>
}