import { authFetch, clearTokens, getAccessToken } from '../auth'

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); this.name = 'ApiError' }
}

export function safeError(status: number, detail?: unknown): string {
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return 'You do not have access to this action.'
  if (status === 404) return 'This item is no longer available.'
  if (status === 429) return 'Too many attempts. Please wait a moment and try again.'
  if (status >= 500) return 'Something went wrong. Please try again shortly.'
  if (status === 422) return 'Please check your selections and try again.'
  const messages: Record<string, string> = {
    'end_time must be after start_time': 'The end time must be later than the start time.',
    'close_time must be after open_time': 'Closing time must be later than opening time.',
    'open_time and close_time are required when is_closed=false': 'Enter opening and closing times for every open day.',
    'Invalid OTP': 'That verification code is incorrect. Please try again.',
    'OTP expired': 'Your verification code has expired. Request a new code.',
    'OTP not requested': 'Request a verification code before continuing.',
    'Gym cannot be submitted': 'This gym cannot be submitted in its current state. Refresh to see its latest status.',
    'Only CONFIRMED bookings can be marked': 'Attendance cannot be recorded for this booking in its current state.'
  }
  if (typeof detail === 'string' && messages[detail]) return messages[detail]
  if (typeof detail === 'string' && detail.length < 220 && !/traceback|sql|exception|<[^>]+>|alembic|database/i.test(detail)) return detail
  return 'Unable to complete this request. Please try again.'
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    // Legacy customer endpoints fall back to a dev account for invalid tokens.
    // Fail closed by checking the strict identity endpoint before accessing them.
    if (/^\/(cart|wallet|profile|customer)(\/|\?|$)/.test(path)) {
      if (!getAccessToken()) throw new ApiError('Please sign in to continue.', 401)
      const identity = await authFetch('/api/v1/users/me', { cache: 'no-store' })
      if (!identity.ok) {
        if (identity.status === 401) clearTokens()
        throw new ApiError(safeError(identity.status), identity.status)
      }
    }
    const headers = new Headers(init?.headers)
    if (init?.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    response = await authFetch(`/api/v1${path}`, { ...init, headers })
  }
  catch (error) {
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('Unable to connect. Check your internet connection and try again.', 0)
  }
  const data: unknown = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 401) clearTokens()
    throw new ApiError(safeError(response.status, data && typeof data === 'object' && 'detail' in data ? data.detail : undefined), response.status)
  }
  if (data === null && response.status !== 204) throw new ApiError('The server returned an unexpected response. Please try again.', response.status)
  return data as T
}

export const post = <T,>(path: string, body?: unknown) => request<T>(path, { method: 'POST', ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
export const money = (value: string | number, currency = 'INR') => new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 2 }).format(Number(value))
export const localDate = (date = new Date()) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
export const dateLabel = (date: string) => new Date(date.length === 10 ? `${date}T12:00:00` : date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })