const ACCESS_KEY = 'fitigo:access_token'
const REFRESH_KEY = 'fitigo:refresh_token'
const AUTH_EVENT = 'fitigo:auth'

export function getAccessToken(): string | null {
  try {
    return window.localStorage.getItem(ACCESS_KEY)
  } catch {
    return null
  }
}

export function setTokens(accessToken: string, refreshToken?: string | null) {
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

export function clearTokens() {
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
  window.addEventListener(AUTH_EVENT, on as EventListener)
  return () => window.removeEventListener(AUTH_EVENT, on as EventListener)
}

export function authFetch(input: RequestInfo | URL, init?: RequestInit) {
  const token = getAccessToken()
  const headers = new Headers(init?.headers || {})
  if (token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`)
  return fetch(input, { ...init, headers })
}
