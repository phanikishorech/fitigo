// Invalidation signals contain no user data and refresh badges across tabs.
const EVENT = 'fitigo:customer-activity'
export type Activity = 'cart' | 'notifications'
export function notifyActivity(kind: Activity) {
  window.dispatchEvent(new CustomEvent(EVENT, { detail: kind }))
  try { localStorage.setItem(EVENT, `${kind}:${Date.now()}:${Math.random()}`) } catch { /* Same-tab updates still work. */ }
}
export function subscribeActivity(handler: (kind: Activity) => void) {
  const local = (event: Event) => handler((event as CustomEvent<Activity>).detail)
  const storage = (event: StorageEvent) => {
    if (event.key !== EVENT) return
    const kind = event.newValue?.split(':')[0]
    if (kind === 'cart' || kind === 'notifications') handler(kind)
  }
  window.addEventListener(EVENT, local); window.addEventListener('storage', storage)
  return () => { window.removeEventListener(EVENT, local); window.removeEventListener('storage', storage) }
}
export async function cartMutation<T>(operation: Promise<T>): Promise<T> {
  const result = await operation
  notifyActivity('cart')
  return result
}