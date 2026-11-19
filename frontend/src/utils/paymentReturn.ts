// Navigation hints, never evidence of payment or authorization to read an order.
const storageKey = 'fitigo:payment-return'
export function rememberPaymentReturn(userId: number, checkoutId: string) {
  try { sessionStorage.setItem(storageKey, JSON.stringify({ userId, checkoutId, at: Date.now() })) } catch { /* Explicit return URL remains available. */ }
}
export function storedPaymentReturn(userId: number): string | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(storageKey) || 'null')
    if (value?.userId !== userId || typeof value.at !== 'number' || Date.now() < value.at || Date.now() - value.at > 3600000) return null
    return paymentReturnReference(`payment_checkout_id=${encodeURIComponent(value.checkoutId)}`).checkoutId
  } catch { return null }
}
export function clearPaymentReturn(checkoutId: string) {
  try { if (JSON.parse(sessionStorage.getItem(storageKey) || 'null')?.checkoutId === checkoutId) sessionStorage.removeItem(storageKey) } catch { /* No storage is required for verification. */ }
}

export function paymentReturnReference(search: string): { requested: boolean; checkoutId: string | null } {
  const query = new URLSearchParams(search)
  const direct = query.get('payment_checkout_id')
  const provider = query.get('order_id')
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
  const hex = provider?.match(/^fitigo_([0-9a-f]{32})$/i)?.[1]
  const derived = hex ? `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}` : null
  const requested = query.has('payment_checkout_id') || query.has('order_id')
  if (query.getAll('payment_checkout_id').length > 1 || query.getAll('order_id').length > 1) return { requested, checkoutId: null }
  if (direct !== null && (!uuid.test(direct) || (provider !== null && derived?.toLowerCase() !== direct.toLowerCase()))) return { requested, checkoutId: null }
  return { requested, checkoutId: direct?.toLowerCase() || derived?.toLowerCase() || null }
}