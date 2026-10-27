import type { AccessCalendar, MembershipSummary } from '../services/accountService'
import { dayPresentation, todayFrom } from './membership'

// Copy only: the backend summary/calendar decide membership and daily access.
export function memberHomePresentation(summary: MembershipSummary, calendar: AccessCalendar) {
  if (!summary.membership_id || !['ACTIVE', 'PAUSED'].includes(summary.status || '')) return null
  const day = todayFrom(calendar)
  if (!day) return null
  const access = dayPresentation(day)
  const multi = summary.membership_scope === 'MULTI_GYM'
  const names = summary.active_gyms.map(gym => gym.gym_name).filter(Boolean)
  const gymName = calendar.gym?.name || names[0]
  const title = multi ? 'You’re a FitiGo member' : names.length > 1 ? 'Your gym memberships are ready to view' : gymName ? `You’re a member of ${gymName}` : 'You have a gym membership'
  if (summary.status === 'PAUSED' || access === 'PAUSED') return { title, status: 'Paused', message: 'Your membership is paused. View My Access for your pause and resumption details.', action: 'View My Access' }
  if (access === 'USED' || access === 'VISITED') return { title, status: 'Used today', message: 'You’ve already used today’s access. View your check-in details in My Access.', action: 'View today’s access' }
  if (access === 'AVAILABLE') return { title, status: 'Available today', message: multi ? 'Your daily visit is included at eligible FitiGo gyms. Generate your personal QR in My Access.' : 'Your membership visit is included. Check today’s access and generate your personal QR.', action: 'Book a visit today' }
  return { title, status: 'Check access', message: 'Check your current membership eligibility in My Access before visiting.', action: 'View My Access' }
}