import { canOpen, isReturnableRoute, roleHome, routePolicy } from './policy'
import { canResumeAction, validatePendingAction, type ActionLocation, type ActionMetadata } from './pendingActions'
import { navigate } from '../router'

const STORAGE_KEY = 'fitigo:return-intent:v1'
const MAX_AGE_MS = 30 * 60 * 1000
const listeners = new Set<() => void>()
let fallback: ReturnIntent | null = null
export type ReturnIntentInput = ActionLocation & { action?: string | null; metadata?: Record<string, unknown> }
export type ReturnIntent = ActionLocation & { id: string; createdAt: number; action: string | null; metadata: ActionMetadata; phase: 'login' | 'returning'; subject: number | null }
const sensitiveKey = /password|passwd|token|secret|credential|authorization|email|phone|mobile|card|cvv|payment|quote|amount/i
const forbiddenValue = /[\\\u0000-\u0020\u007f]/
export function currentLocation(): ActionLocation {
  return { pathname: window.location.pathname, search: window.location.search, hash: window.location.hash }
}
export function locationUrl(location: ActionLocation) { return location.pathname + location.search + location.hash }
export function validateReturnPath(value: unknown): ActionLocation | null {
  if (typeof value !== 'string' || value.length > 4096 || !value.startsWith('/') || value.startsWith('//') || forbiddenValue.test(value)) return null
  try {
    const url = new URL(value, 'https://fitigo.invalid')
    if (url.origin !== 'https://fitigo.invalid' || url.username || url.password) return null
    // Reject rather than reinterpret normalized/encoded paths (including slash,
    // dot-segment and backslash redirect tricks). Existing routes need none of these.
    const rawPath = value.split(/[?#]/)[0]
    if (url.pathname !== rawPath || /%|\/\//.test(rawPath) || !isReturnableRoute(rawPath)) return null
    const decodedSearch = decodeURIComponent(url.search)
    const decodedHash = decodeURIComponent(url.hash)
    if (/[\\\u0000-\u001f\u007f]/.test(decodedSearch + decodedHash)) return null
    if ([...url.searchParams.keys()].some(key => sensitiveKey.test(key))) return null
    const hashParams = new URLSearchParams(decodedHash.slice(1))
    if ((decodedHash.includes('=') && [...hashParams.keys()].some(key => sensitiveKey.test(key))) || /(?:bearer\s|GYMACCESS:)/i.test(decodedSearch + decodedHash)) return null
    return { pathname: rawPath, search: url.search, hash: url.hash }
  } catch { return null }
}
function notify() { listeners.forEach(listener => listener()) }
function write(value: ReturnIntent | null) {
  fallback = value
  try { if (value) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value)); else sessionStorage.removeItem(STORAGE_KEY) } catch { /* In-memory continuation still works if storage is unavailable. */ }
  notify()
}
export function clearReturnIntent(id?: string) {
  if (id && getReturnIntent()?.id !== id) return
  write(null)
}
export function getReturnIntent(): ReturnIntent | null {
  let raw: unknown = fallback
  try {
    const serialized = sessionStorage.getItem(STORAGE_KEY)
    try { raw = serialized ? JSON.parse(serialized) : null } catch { write(null); return null }
  } catch { /* Fall back only when browser storage cannot be read. */ }
  if (!raw || typeof raw !== 'object') { if (raw !== null) write(null); return null }
  const item = raw as ReturnIntent
  const location = typeof item.pathname === 'string' && typeof item.search === 'string' && typeof item.hash === 'string' ? validateReturnPath(locationUrl(item)) : null
  const now = Date.now()
  if (!location || location.pathname !== item.pathname || location.search !== item.search || location.hash !== item.hash ||
      typeof item.id !== 'string' || !/^[\w-]{1,80}$/.test(item.id) || typeof item.createdAt !== 'number' || !Number.isFinite(item.createdAt) || now - item.createdAt > MAX_AGE_MS || item.createdAt > now + 1000 ||
      !['login', 'returning'].includes(item.phase) || (item.subject !== null && (!Number.isSafeInteger(item.subject) || item.subject < 1))) {
    write(null); return null
  }
  const action = validatePendingAction(item.action, item.metadata, location)
  return { ...location, id: item.id, createdAt: item.createdAt, phase: item.phase, subject: item.subject, action: action?.action || null, metadata: action?.metadata || {} }
}
export function saveReturnIntent(input: ReturnIntentInput, preserveAction = false): ReturnIntent | null {
  const location = validateReturnPath(locationUrl(input))
  if (!location) { clearReturnIntent(); return null }
  const existing = getReturnIntent()
  if (preserveAction && existing?.phase === 'login' && locationUrl(existing) === locationUrl(location)) return existing
  const action = validatePendingAction(input.action, input.metadata || {}, location)
  const intent: ReturnIntent = { ...location, id: crypto.randomUUID(), createdAt: Date.now(), action: action?.action || null, metadata: action?.metadata || {}, phase: 'login', subject: null }
  write(intent); return intent
}
export function requestAuthentication(input: Partial<ReturnIntentInput> = {}, expired = false) {
  const location = { ...currentLocation(), ...input }
  if (!routePolicy(window.location.pathname).login) saveReturnIntent(location, !input.action)
  navigate(expired ? '/login?expired=1' : '/login', true)
}
export function importLoginReturnParameter() {
  if (!routePolicy(window.location.pathname).login || getReturnIntent()) return
  const value = new URLSearchParams(window.location.search).get('returnTo')
  if (value === null) return
  const location = validateReturnPath(value)
  if (location) saveReturnIntent(location)
  else clearReturnIntent()
}
export function handlePostLoginRedirect(identity: { user: { id: number }; roles: string[] }) {
  importLoginReturnParameter()
  const intent = getReturnIntent()
  if (!intent || !canOpen(identity.roles, intent.pathname) || (intent.subject !== null && intent.subject !== identity.user.id)) {
    clearReturnIntent(); navigate(roleHome(identity.roles)!, true); return
  }
  const actionAllowed = intent.action && canResumeAction(intent.action, identity.roles)
  write({ ...intent, phase: 'returning', subject: identity.user.id, action: actionAllowed ? intent.action : null, metadata: actionAllowed ? intent.metadata : {} })
  navigate(locationUrl(intent), true)
}
export function consumeReturnIntent(id: string, identity: { user: { id: number }; roles: string[] }): ReturnIntent | null {
  const intent = getReturnIntent()
  if (!intent || intent.id !== id || intent.phase !== 'returning' || intent.subject !== identity.user.id || locationUrl(intent) !== locationUrl(currentLocation()) || !canOpen(identity.roles, intent.pathname)) return null
  if (intent.action && !canResumeAction(intent.action, identity.roles)) { clearReturnIntent(id); return null }
  // Claim before invoking an existing handler: StrictMode, rerenders or refresh
  // cannot replay an action. Normal page errors/retry remain owned by that page.
  clearReturnIntent(id)
  return intent
}
export function subscribeReturnIntent(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } }