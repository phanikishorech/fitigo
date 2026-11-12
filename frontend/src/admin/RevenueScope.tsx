export default function RevenueScope({ mode }: { mode?: string }) {
  return <p className="ad-card-subtitle" role="note">
    {mode === 'test' ? 'Test scope · No real money.' : mode === 'live' ? 'Live scope · Test payments excluded.' : 'Payment scope unavailable; refresh before relying on totals.'}
    {' '}Verified INR gateway booking payments, grouped by scheduled booking date. Cancelled/no-show bookings remain included while paid; these are not earned-revenue or settlement totals. Refunds, partial refunds, review-required, wallet and unclassified legacy payments are excluded. Booking counts cover all modes.
  </p>
}