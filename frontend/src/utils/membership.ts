import type { AccessCalendar, AccessDay } from '../services/accountService'

export type AccessPresentation = 'AVAILABLE' | 'USED' | 'VISITED' | 'PAUSED' | 'CONSUMED' | 'EXPIRED' | 'UNAVAILABLE' | 'FUTURE' | 'NONE'

// Presentation of returned membership statuses, not an eligibility/date calculation.
// Unknown statuses must not be interpreted as an invitation to buy another plan.
export function membershipOverviewState(records: { status: string }[], summaryStatus: string | null): 'active' | 'none' | 'unknown' {
  if (['ACTIVE', 'PAUSED'].includes(summaryStatus || '') || records.some(record => ['ACTIVE', 'PAUSED'].includes(record.status))) return 'active'
  const nonActive = ['PAUSED', 'EXPIRED', 'INACTIVE', 'CANCELLED', 'TRANSFERRED', 'NONE']
  if ((summaryStatus === null || nonActive.includes(summaryStatus)) && records.every(record => nonActive.includes(record.status))) return 'none'
  return 'unknown'
}

// Group only explicit past/inactive statuses. Pending and unknown records stay
// visible; never infer expiry or access eligibility from dates on the device.
export function groupMembershipRecords<T extends { status: string }>(records: T[]): { current: T[]; history: T[] } {
  const current: T[] = []; const history: T[] = []
  for (const record of records) {
    if (['EXPIRED', 'CANCELLED', 'INACTIVE', 'TRANSFERRED', 'NONE'].includes(record.status)) history.push(record)
    else current.push(record)
  }
  return { current, history }
}
// Presentation only. No dates, membership counts or expiry arithmetic determine entitlement.
export function dayPresentation(day: AccessDay): AccessPresentation {
  if (day.status === 'VISITED' || (day.qr_status === 'USED' && !!day.checkin_time)) return 'VISITED'
  if (day.qr_status === 'USED') return 'USED'
  if (day.status === 'PAUSED' || day.qr_status === 'PAUSED') return 'PAUSED'
  if (day.status === 'NO_VISIT' || day.status === 'CONSUMED') return 'CONSUMED'
  if (day.qr_status === 'EXPIRED' || day.status === 'EXPIRED') return 'EXPIRED'
  if (day.qr_available && day.qr_status === 'ACTIVE') return 'AVAILABLE'
  if (day.status === 'FUTURE') return 'FUTURE'
  if (day.status === 'NONE') return 'NONE'
  return 'UNAVAILABLE'
}
export function todayFrom(calendar: AccessCalendar) { return calendar.days.find(day => day.status === 'TODAY') }
export function hasAvailableAccess(calendar: AccessCalendar) {
  const today = todayFrom(calendar)
  return !!today && dayPresentation(today) === 'AVAILABLE'
}
export const accessLabels: Record<AccessPresentation, string> = {
  AVAILABLE: 'Available', USED: 'Already used', VISITED: 'Visited', PAUSED: 'Paused',
  CONSUMED: 'No visit · Access consumed', EXPIRED: 'Expired', UNAVAILABLE: 'Unavailable', FUTURE: 'Future date', NONE: 'No access day'
}
export function utcTimestamp(value: string) {
  return /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`
}
export function membershipDate(value: string) {
  return new Date(value.length === 10 ? `${value}T12:00:00+05:30` : utcTimestamp(value)).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata' })
}
export function membershipTime(value: string) {
  return new Date(utcTimestamp(value)).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' })
}

export function istDateTime(value: string) {
  return `${membershipDate(value)}, ${membershipTime(value)} IST`
}