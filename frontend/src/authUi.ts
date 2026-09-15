const OPEN_AUTH_EVENT = 'fitigo:open_auth'

export function openAuthModal(intent: string) {
  window.dispatchEvent(new CustomEvent(OPEN_AUTH_EVENT, { detail: { intent } }))
}

export function subscribeOpenAuthModal(handler: (intent: string) => void) {
  const on = (e: Event) => {
    const ce = e as CustomEvent
    handler(String((ce as any)?.detail?.intent ?? 'unknown'))
  }
  window.addEventListener(OPEN_AUTH_EVENT, on as EventListener)
  return () => window.removeEventListener(OPEN_AUTH_EVENT, on as EventListener)
}
