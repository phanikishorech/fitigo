import { accessService, type AccessCalendar } from './accountService'
import { gymService } from './gymService'
import type { GymDetailsResponse } from '../screens/GymDetails/types'
import { todayFrom } from '../utils/membership'

export type VisitAccessDecision = 'MEMBERSHIP' | 'ALREADY_USED' | 'PAID_BOOKING'
export type VisitAccess =
  | { gym: GymDetailsResponse; calendar: AccessCalendar; decision: 'MEMBERSHIP' | 'ALREADY_USED' }
  | { gym: GymDetailsResponse; calendar: AccessCalendar | null; decision: 'PAID_BOOKING' }

const paidBookingStates = ['NO_ACTIVE_MEMBERSHIP', 'DAY_PASS_AVAILABLE', 'UPGRADE_REQUIRED', 'UNAVAILABLE']

// Translate explicit server states to navigation only. Never infer membership from
// dates, prices, active-plan counts, or a locally maintained list of partner gyms.
export function visitAccessDecision(gym: GymDetailsResponse, calendar: AccessCalendar | null): VisitAccessDecision {
  const inclusion = gym.membership_access?.status
  if (paidBookingStates.includes(inclusion)) return 'PAID_BOOKING'
  if (inclusion !== 'INCLUDED') throw new Error('Unable to check your membership access.')
  if (!calendar) throw new Error('Unable to check your membership access.')
  const today = todayFrom(calendar)
  if (!today) throw new Error('Unable to check your membership access.')
  if (today.qr_status === 'USED') return 'ALREADY_USED'
  if (['PAUSED', 'EXPIRED', 'NO_ACCESS', 'REVOKED'].includes(today.qr_status || '')) return 'PAID_BOOKING'
  if (today.qr_status !== 'ACTIVE' || !today.qr_available) throw new Error('Unable to check your membership access.')
  if (calendar.access_type === 'SINGLE_GYM') {
    if (!calendar.gym) throw new Error('Unable to check your membership access.')
    return calendar.gym.id === gym.gym_id ? 'MEMBERSHIP' : 'PAID_BOOKING'
  }
  if (calendar.access_type === 'MULTI_GYM') return 'MEMBERSHIP'
  throw new Error('Unable to check your membership access.')
}

export const visitAccessService = {
  check: async (gymId: number): Promise<VisitAccess> => {
    const gym = await gymService.accessDetails(gymId)
    // A successful selected-gym response already resolves non-member/ineligible
    // routing. Do not require a membership-only calendar for normal paid bookings.
    // null here explicitly means "not requested", never loading or a failed read.
    if (paidBookingStates.includes(gym.membership_access?.status)) {
      return { gym, calendar: null, decision: 'PAID_BOOKING' }
    }
    if (gym.membership_access?.status !== 'INCLUDED') throw new Error('Unable to check your membership access.')
    const calendar = await accessService.current()
    return { gym, calendar, decision: visitAccessDecision(gym, calendar) }
  }
}
export function visitDestination(gymId: number, decision: VisitAccessDecision) {
  // Only called for non-membership decisions or after an explicit membership choice.
  // Already-used personal access remains distinct for My Access rendering, but a
  // new Book a Visit request must go to the ordinary paid booking flow.
  return decision === 'MEMBERSHIP' ? `/my-access?gymId=${gymId}` : `/gyms/${gymId}/book/access`
}