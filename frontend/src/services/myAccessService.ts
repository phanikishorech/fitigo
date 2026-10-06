import { accessService, membershipService, profileService, type AccessCalendar } from './accountService'
import { gymService } from './gymService'
import { membershipPauseService } from './membershipPauseService'
import { dayPresentation, todayFrom } from '../utils/membership'

// Compose existing read-only contracts. Eligibility and membership scope are
// supplied by the backend; this service never calculates dates or grants access.
export function validateAccessCalendar(calendar: AccessCalendar) {
  const day = todayFrom(calendar)
  if (!day || !['ACTIVE', 'USED', 'PAUSED', 'EXPIRED', 'NO_ACCESS', 'REVOKED'].includes(day.qr_status || '')) throw new Error('Unable to load access status.')
  if (day.qr_status === 'ACTIVE' && (!day.qr_available || !['SINGLE_GYM', 'MULTI_GYM'].includes(calendar.access_type || ''))) throw new Error('Unable to load access status.')
  if (day.qr_status === 'ACTIVE' && calendar.access_type === 'SINGLE_GYM' && (!calendar.gym?.id || !calendar.gym.name)) throw new Error('Unable to load assigned gym information.')
  return day
}

export const myAccessService = {
  current: async () => {
    const [calendar, summary, memberships, customer] = await Promise.all([
      accessService.current(), membershipService.summary(), membershipService.mine(), profileService.me(),
    ])
    const day = validateAccessCalendar(calendar)
    const membership = memberships.find(item => item.id === summary.membership_id)
    const type = calendar.access_type || summary.membership_scope
    const gymId = type === 'SINGLE_GYM' ? calendar.gym?.id || membership?.gym_id : null
    const [gym, pause] = await Promise.all([
      gymId ? gymService.accessDetails(gymId) : null,
      dayPresentation(day) === 'PAUSED' && summary.membership_id ? membershipPauseService.eligibility(summary.membership_id) : null,
    ])
    return { calendar, summary, customer, type, gym, pause }
  },
}
export type MyAccessData = Awaited<ReturnType<typeof myAccessService.current>>