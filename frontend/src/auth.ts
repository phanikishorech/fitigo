const ACCESS_KEY = 'fitigo:access_token'
const REFRESH_KEY = 'fitigo:refresh_token'
const AUTH_EVENT = 'fitigo:auth'
let authReason: 'signedOut' | 'expired' = 'signedOut'
export const getAuthReason = () => authReason

export function getAccessToken(): string | null {
  try {
    return window.localStorage.getItem(ACCESS_KEY)
  } catch {
    return null
  }
}

export function setTokens(accessToken: string, refreshToken?: string | null) {
  authReason = 'signedOut'
  try {
    window.localStorage.setItem(ACCESS_KEY, accessToken)
    if (typeof refreshToken !== 'undefined') {
      if (refreshToken) window.localStorage.setItem(REFRESH_KEY, refreshToken)
      else window.localStorage.removeItem(REFRESH_KEY)
    }
  } catch {
    // ignore
  }
  window.dispatchEvent(new CustomEvent(AUTH_EVENT))
}

export function clearTokens(reason: 'signedOut' | 'expired' = 'signedOut') {
  authReason = reason
  try {
    window.localStorage.removeItem(ACCESS_KEY)
    window.localStorage.removeItem(REFRESH_KEY)
  } catch {
    // ignore
  }
  window.dispatchEvent(new CustomEvent(AUTH_EVENT))
}

export function subscribeAuth(handler: () => void) {
  const on = () => handler()
  const onStorage = (event: StorageEvent) => { if (event.key === ACCESS_KEY || event.key === REFRESH_KEY || event.key === null) { authReason = 'signedOut'; handler() } }
  window.addEventListener(AUTH_EVENT, on as EventListener)
  window.addEventListener('storage', onStorage)
  return () => { window.removeEventListener(AUTH_EVENT, on as EventListener); window.removeEventListener('storage', onStorage) }
}

export function authFetch(input: RequestInfo | URL, init?: RequestInit) {
  const token = getAccessToken()
  const headers = new Headers(init?.headers || {})
  if (token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`)
  return fetch(input, { ...init, headers })
}
