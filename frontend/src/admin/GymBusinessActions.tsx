import { useState } from 'react'
import './agreements.css'
import { adminReactivateGym, adminSuspendGym } from '../screens/Admin/api'
import { Button, ConfirmationModal, DataCard, Link, Resource } from './UI'
import { gymService } from './services'
import { useAdminResource } from './hooks'
export default function GymBusinessActions({ id, onChanged }: { id: number; onChanged: () => void }) {
  const resource = useAdminResource(() => gymService.details(id), `gym-business-actions:${id}`)
  const [action, setAction] = useState<'suspend' | 'reactivate' | null>(null)
  return <DataCard title="Gym activity"><div className="ag-actions"><Link to={`/admin/bookings?gym_id=${id}`}>Bookings</Link><Link to={`/admin/reports?gym_id=${id}`}>Visits and revenue reports</Link><Link to={`/admin/memberships?gym_id=${id}`}>Memberships</Link></div><Resource resource={resource}>{gym => <>{gym.status === 'APPROVED' && <Button variant="secondary" onClick={() => setAction('suspend')}>Deactivate gym</Button>}{gym.status === 'SUSPENDED' && <Button variant="secondary" onClick={() => setAction('reactivate')}>Reactivate gym</Button>}</>}</Resource>{action && <ConfirmationModal title={action === 'suspend' ? 'Deactivate gym?' : 'Reactivate gym?'} confirm={action === 'suspend' ? 'Deactivate' : 'Reactivate'} reason="required" onClose={() => setAction(null)} action={reason => action === 'suspend' ? adminSuspendGym(id, reason) : adminReactivateGym(id)} success="Gym status updated." onSuccess={onChanged}><p>This uses the existing gym approval and availability rules.</p></ConfirmationModal>}</DataCard>
}