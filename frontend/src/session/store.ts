import { clearTokens, getAccessToken, getAuthReason, setTokens, subscribeAuth } from '../auth'
import { ApiError, request } from '../services/client'
import { clearReadCache } from '../services/readCache'
import { navigate } from '../router'
import type { AuthTokens } from '../components/AuthModal/AuthModal'
import type { User } from '../services/accountService'
import { backendRoles, routePolicy } from './policy'
import { clearReturnIntent, currentLocation, handlePostLoginRedirect, saveReturnIntent } from './returnIntent'

export type Identity = { user: User; roles: string[] }
export type SessionState =
  | { status: 'loading' | 'anonymous' | 'expired' | 'invalid-role' | 'forbidden' }
  | { status: 'authenticated'; identity: Identity }
  | { status: 'error'; message: string }
let state: SessionState = { status: 'loading' }
const listeners = new Set<() => void>()
let version = 0
let suppressed = false
let activeRead: Promise<void> | null = null
let activeToken: string | null = null
let verifiedToken: string | null = null
export const getSession = () => state
export function subscribeSession(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } }
function publish(next: SessionState) { state = next; listeners.forEach(listener => listener()) }
function acceptIdentity(data: unknown) {
  if (!data || typeof data !== 'object') { publish({ status: 'error', message: 'The server returned an incomplete session. Please try again.' }); return }
  const raw = data as Record<string, unknown>
  const roles = backendRoles(raw.roles)
  if (!roles) { publish({ status: 'invalid-role' }); return }
  const user = raw.user as User | undefined
  if (!user || !Number.isSafeInteger(user.id) || user.id < 1 || typeof user.email !== 'string') { publish({ status: 'error', message: 'The server returned an incomplete session. Please try again.' }); return }
  if ('status' in user && user.status !== 'ACTIVE') { publish({ status: 'forbidden' }); return }
  publish({ status: 'authenticated', identity: { user, roles } })
}
export function restoreSession(): Promise<void> {
  const token = getAccessToken()
  if (!token) {
    if (getAuthReason() === 'expired' && !routePolicy(window.location.pathname).login) saveReturnIntent(currentLocation(), true)
    version++; activeRead = null; activeToken = null; verifiedToken = null
    publish({ status: getAuthReason() === 'expired' ? 'expired' : 'anonymous' })
    return Promise.resolve()
  }
  if (activeRead && activeToken === token) return activeRead
  const operation = ++version; activeToken = token
  // Revalidate on focus without tearing down a verified page (notably its camera).
  // A changed token or initial restoration still blocks rendering until verified.
  if (state.status !== 'authenticated' || token !== verifiedToken) publish({ status: 'loading' })
  activeRead = request<Identity>('/auth/session', { cache: 'no-store', signal: AbortSignal.timeout(12000) }).then(data => {
    if (operation === version && token === getAccessToken()) { verifiedToken = token; acceptIdentity(data) }
  }).catch(error => {
    if (operation !== version) return
    if (error instanceof ApiError && error.status === 401) publish({ status: 'expired' })
    else if (error instanceof ApiError && error.status === 403) publish({ status: 'forbidden' })
    else publish({ status: 'error', message: error instanceof ApiError && error.status === 0 ? 'Unable to connect. Check your connection and retry session verification.' : 'Unable to verify your session. Please try again.' })
  }).finally(() => { if (operation === version) activeRead = null })
  return activeRead
}
export function startSessionTracking() {
  const unsubscribe = subscribeAuth(() => { if (!suppressed) { clearReadCache(); void restoreSession() } })
  void restoreSession()
  const focus = () => { if (!document.hidden && getAccessToken()) void restoreSession() }
  window.addEventListener('focus', focus)
  return () => { unsubscribe(); window.removeEventListener('focus', focus) }
}
export async function completeLogin(tokens: AuthTokens) {
  if (!tokens || typeof tokens.access_token !== 'string' || !tokens.access_token || typeof tokens.refresh_token !== 'string' || !tokens.refresh_token) {
    publish({ status: 'error', message: 'The server returned an incomplete sign-in response. Please try again.' }); return
  }
  version++; activeRead = null
  suppressed = true
  try { setTokens(tokens.access_token, tokens.refresh_token); clearReadCache() } finally { suppressed = false }
  // New login/OTP responses include identity. Older backend responses are verified
  // through the same authoritative session endpoint, never local role hints.
  if (tokens.roles !== undefined && tokens.user !== undefined) { verifiedToken = tokens.access_token; acceptIdentity(tokens) }
  else await restoreSession()
  const result = getSession()
  if (result.status === 'authenticated') handlePostLoginRedirect(result.identity)
}
export async function logoutSession() {
  let refresh: string | null = null
  try { refresh = localStorage.getItem('fitigo:refresh_token') } catch { /* storage unavailable */ }
  // Start revocation with existing credentials; local sign-out must work offline.
  const revocation = refresh ? request('/auth/logout', { method: 'POST', body: JSON.stringify({ refresh_token: refresh }), signal: AbortSignal.timeout(8000) }).catch(() => null) : Promise.resolve()
  navigate('/login', true)
  version++; activeRead = null; clearReturnIntent(); clearReadCache(); clearTokens(); publish({ status: 'anonymous' })
  await revocation
}