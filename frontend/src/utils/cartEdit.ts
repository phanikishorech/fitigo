import type { CartItemResponse } from '../screens/GymAccess/types'
import type { BookingDraft } from '../store/bookingStore'

export function cartEditDraft(item: CartItemResponse): BookingDraft {
  if (!['GYM', 'CLASS'].includes(item.booking_type)) throw new Error('Unsupported visit type.')
  return { gymId: item.gym_id, accessType: item.booking_type as 'GYM' | 'CLASS', date: item.booking_date,
    memberCount: item.member_count, start: (item.preferred_start_time || item.start_time || '').slice(0, 5),
    end: (item.preferred_end_time || item.end_time || '').slice(0, 5), classId: item.class_session_id ?? null }
}