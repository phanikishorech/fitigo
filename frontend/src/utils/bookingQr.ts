import type { BookingAccess, BookingQr } from '../services/bookingService'

export function hasBookingCheckin(pass: { status: string; checked_in_at?: string | null }) {
  return pass.status === 'USED' && !!pass.checked_in_at && Number.isFinite(Date.parse(pass.checked_in_at))
}

// Only a matching server-recorded check-in confirms admission. A used-status
// message, an expired timer or a missing pass is not proof of a successful scan.
export function reconcileBookingQr(qr: BookingQr, access: BookingAccess): BookingQr | null {
  const passes = qr.passes.map(pass => {
    const current = access.passes.find(row => row.qr_id === pass.qr_id)
    return {
      ...pass,
      status: current?.status || 'REVOKED',
      checked_in_at: current?.checked_in_at || null,
      qr_token: access.qr_available && current?.status === 'ACTIVE' ? pass.qr_token : null,
    }
  })
  if (!access.qr_available && !(access.status === 'BOOKING_ALREADY_USED' && passes.length > 0 && passes.every(hasBookingCheckin))) return null
  return { ...qr, passes }
}