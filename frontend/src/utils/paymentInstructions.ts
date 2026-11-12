export function paymentInstructions(catalog: { checkout_available: boolean; payment_mode?: string }) {
  if (!catalog.checkout_available) return 'Membership checkout is unavailable in this environment. No payment will be taken.'
  if (catalog.payment_mode === 'CASHFREE') return 'Cashfree checkout is available. Review the amount and sandbox/live mode at checkout; membership activates only after server verification.'
  if (catalog.payment_mode === 'RAZORPAY') return 'Razorpay checkout is available. Review the amount and test/live mode at checkout; membership activates only after server verification.'
  if (catalog.payment_mode === 'WALLET_TEST_CREDIT') return 'Development wallet test credits are enabled. They are not real-money payments. Review the current balance and price at checkout.'
  return 'Review the backend-confirmed payment method and availability at checkout. No payment is taken by selecting a plan.'
}