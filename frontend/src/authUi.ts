const OPEN_AUTH_EVENT = 'fitigo:open_auth'
import { requestAuthentication, validateReturnPath, type ReturnIntentInput } from './session/returnIntent'
import { routePolicy } from './session/policy'
import { getAccessToken } from './auth'
import { restoreSession } from './session/store'

export function openAuthModal(intent?: string | Partial<ReturnIntentInput>) {
  if (!routePolicy(window.location.pathname).login) {
    // A token may disappear before the cross-tab/session event is delivered.
    // Synchronize the shared identity rather than bouncing straight back from login.
    if (!getAccessToken()) void restoreSession()
    // Retain legacy intent labels as plain current-page continuation. Explicit
    // internal destinations remain supported; new actions use the typed model.
    const location = typeof intent === 'string' ? validateReturnPath(intent) : intent
    requestAuthentication(location || {})
    return
  }
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
