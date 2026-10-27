export function isBookableSession(status: string, capacity: number) {
  return ['AVAILABLE', 'FEW_SLOTS_LEFT'].includes(status) && capacity > 0
}

// A selected clock time is always IST, never the browser's local timezone.
export function isFutureBookingStart(date: string, time: string, now = Date.now()) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}(:\d{2})?$/.test(time)) return false
  const start = Date.parse(`${date}T${time.length === 5 ? `${time}:00` : time}+05:30`)
  return Number.isFinite(start) && start > now
}

export function minimumBookingStart(date: string, opening: string | null | undefined, now = Date.now()) {
  const today = istDateKey(now)
  const next = Math.floor(now / 60000) * 60000 + 60000
  const nextMinute = `${istDateKey(next)}T${new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(next)}`
  const earliest = date === today ? (nextMinute.slice(0, 10) === today ? nextMinute.slice(11, 16) : '23:59') : '00:00'
  return [opening?.slice(0, 5) || '00:00', earliest].sort().at(-1)!
}

export function istDateKey(now = Date.now()) {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now)
  return ['year', 'month', 'day'].map(type => parts.find(part => part.type === type)!.value).join('-')
}

export function oneHourVisitEnd(start: string): string {
  if (!/^\d{2}:(00|15|30|45)$/.test(start)) return ''
  const hour = Number(start.slice(0, 2))
  if (hour < 0 || hour >= 23) return ''
  return `${String(hour + 1).padStart(2, '0')}:${start.slice(3)}`
}

export function gymStartOptions(date: string, opening: string | null | undefined, closing: string | null | undefined, now = Date.now()): string[] {
  if (!opening || !closing || opening >= closing) return []
  return Array.from({ length: 24 * 4 }, (_, index) => `${String(Math.floor(index / 4)).padStart(2, '0')}:${String(index % 4 * 15).padStart(2, '0')}`)
    .filter(start => {
      const end = oneHourVisitEnd(start)
      return end && `${start}:00` >= (opening.length === 5 ? `${opening}:00` : opening) && `${end}:00` <= (closing.length === 5 ? `${closing}:00` : closing) && isFutureBookingStart(date, start, now)
    })
}
export function amountInMinorUnits(value: string | number): number {
  const amount = Number(value)
  if (!Number.isFinite(amount) || amount < 0) throw new Error('Invalid amount returned by server.')
  return Math.round(amount * 100)
}
export function canReview(visit: { booking_id: number; attendance_status: string | null; booking_status: string; can_review?: boolean; membership_covered?: boolean }) {
  return visit.can_review === true && visit.booking_id > 0 && !visit.membership_covered && ['CONFIRMED', 'COMPLETED'].includes(visit.booking_status)
}