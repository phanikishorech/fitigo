import { useState } from 'react'
import * as api from '../screens/GymOwner/api'
import { useMutation, useResource } from '../hooks/useResource'
import { Button, Card, ErrorState, Notice, Skeleton } from './UI'

export default function StaffInvitations({ gymId }: { gymId: number }) {
  const [open, setOpen] = useState(false)
  return <Card title="Pending invitations"><p>New staff receive access only after accepting their invitation.</p><Button variant="secondary" onClick={() => setOpen(value => !value)}>{open ? 'Hide invitations' : 'Manage invitations'}</Button>{open && <InvitationList gymId={gymId} />}</Card>
}

function InvitationList({ gymId }: { gymId: number }) {
  const result = useResource(() => api.listStaffInvitations(gymId), String(gymId))
  const mutation = useMutation(); const [message, setMessage] = useState('')
  return <div className="ow-stack">
    {message && <Notice>{message}</Notice>}{mutation.error && <Notice tone="error">{mutation.error}</Notice>}
    {result.loading ? <Skeleton /> : result.error ? <ErrorState message={result.error} retry={result.retry} /> : result.data?.length ? result.data.map(row => <div className="ow-stack" key={row.id}>
      <strong>{row.email}</strong><span>{row.status} · Expires {new Date(row.expires_at).toLocaleString()}</span>
      <div className="ow-actions"><Button disabled={mutation.pending} onClick={() => void mutation.run(async () => { await api.inviteStaff(gymId, { email: row.email }); setMessage('Replacement invitation accepted by the email provider. The previous link is no longer valid.'); result.retry() })}>Resend invitation</Button>
      <Button variant="danger" disabled={mutation.pending} onClick={() => void mutation.run(async () => { await api.revokeStaffInvitation(gymId, row.id); setMessage('Invitation revoked.'); result.retry() })}>Revoke invitation</Button></div>
    </div>) : <p>No pending invitations.</p>}
  </div>
}