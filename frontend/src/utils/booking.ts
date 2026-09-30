export function isBookableSession(status: string, capacity: number) {
  return ['AVAILABLE', 'FEW_SLOTS_LEFT'].includes(status) && capacity > 0
}
export function amountInMinorUnits(value: string | number): number {
  const amount = Number(value)
  if (!Number.isFinite(amount) || amount < 0) throw new Error('Invalid amount returned by server.')
  return Math.round(amount * 100)
}
export function canReview(visit: { booking_id: number; attendance_status: string | null; booking_status: string }) {
  return visit.booking_id > 0 && visit.attendance_status === 'ATTENDED' && ['CONFIRMED', 'COMPLETED'].includes(visit.booking_status)
}