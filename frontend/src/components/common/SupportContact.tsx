import { useResource } from '../../hooks/useResource'
import { request } from '../../services/client'
import SupportRequests, { type SupportPrefill } from './SupportRequests'

export default function SupportContact({ prefill }: { prefill?: SupportPrefill }) {
  const resource=useResource(() => request<{ email: string | null; message: string }>('/meta/support', { cache: 'no-store' }), 'support-contact')
  return <section><h3>Support</h3>{resource.loading ? <p>Checking support contact…</p> : resource.error ? <p>Support contact could not be loaded. <button type="button" onClick={resource.retry}>Retry</button></p> : <p>{resource.data?.email ? <a href={`mailto:${resource.data.email}`}>{resource.data.email}</a> : resource.data?.message}</p>}<p>Never send passwords, OTP codes, QR tokens or payment credentials to support.</p><SupportRequests prefill={prefill} /></section>
}