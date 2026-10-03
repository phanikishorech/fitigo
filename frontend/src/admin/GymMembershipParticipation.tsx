import { useState } from 'react'
import { request } from '../services/client'
import { useAdminResource } from './hooks'
import { Alert, Button, ConfirmationModal, DataCard, Resource, StatusBadge } from './UI'

type Participation = { gym_id: number; enabled: boolean }
const participationService = {
  get: (id: number) => request<Participation>(`/admin/gyms/${id}/multi-gym-participation`, { cache: 'no-store' }),
  set: (id: number, enabled: boolean) => request<Participation>(`/admin/gyms/${id}/multi-gym-participation`, { method: 'PUT', body: JSON.stringify({ enabled }) }),
}
export default function GymMembershipParticipation({ id }: { id: number }) {
  const resource = useAdminResource(() => participationService.get(id), `gym-participation:${id}`)
  const [confirm, setConfirm] = useState(false)
  return <DataCard title="Multi-Gym participation"><Resource resource={resource}>{data => <>
    <StatusBadge status={data.enabled ? 'ACTIVE' : 'INACTIVE'} /><p className="ad-description">Only approved, enabled gyms opted in here accept Multi-Gym memberships. Existing Single-Gym memberships are unchanged.</p>
    <Alert>Controlled MVP uses test wallet credits only. Enabling participation does not enable external payments.</Alert>
    <Button variant={data.enabled ? 'danger' : 'secondary'} onClick={() => setConfirm(true)}>{data.enabled ? 'Disable Multi-Gym Access' : 'Enable Multi-Gym Access'}</Button>
    {confirm && <ConfirmationModal title={data.enabled ? 'Disable Multi-Gym access?' : 'Enable Multi-Gym access?'} confirm="Confirm participation change" danger={data.enabled} onClose={() => setConfirm(false)} action={() => participationService.set(id, !data.enabled)} success="Gym participation updated." onSuccess={resource.retry}>
      {data.enabled ? 'Multi-Gym customers will no longer be able to check in here, including with previously generated QR codes.' : 'Multi-Gym members will be able to use their daily access at this approved gym.'}
    </ConfirmationModal>}
  </>}</Resource></DataCard>
}