import type { StaffAssignment } from '../screens/GymOwner/api'
import { istDateTime } from '../utils/membership'
import { StatusBadge } from './UI'

export function staffName(staff: StaffAssignment) {
  return [staff.first_name?.trim(), staff.last_name?.trim()].filter(Boolean).join(' ') || staff.email || `Staff #${staff.user_id}`
}

export default function StaffIdentity({ staff }: { staff: StaffAssignment }) {
  return <div className="ow-staff-identity">
    <div className="ow-staff-heading"><span className="ow-avatar" aria-hidden="true">{staffName(staff).slice(0, 1)}</span><div><h2>{staffName(staff)}</h2><small className="ow-muted">Staff #{staff.user_id} · Assignment #{staff.id}</small></div></div>
    <dl className="ow-staff-details">
      <div><dt>Email</dt><dd>{staff.email || 'Not provided'}</dd></div>
      <div><dt>Phone</dt><dd>{staff.phone || 'Not provided'}</dd></div>
      <div><dt>Assigned role</dt><dd><StatusBadge status={staff.role} /></dd></div>
      <div><dt>Account status</dt><dd>{staff.account_status ? <StatusBadge status={staff.account_status} /> : 'Account unavailable'}</dd></div>
      <div><dt>Access assigned</dt><dd>{staff.assigned_at ? istDateTime(staff.assigned_at) : 'Not recorded'}</dd></div>
    </dl>
  </div>
}