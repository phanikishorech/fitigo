import { authFetch, clearTokens, getAccessToken } from '../auth'

export class ApiError extends Error {
  constructor(message: string, public status: number, public code?: string) { super(message); this.name = 'ApiError' }
}

// Only recognized public business codes are exposed; never retain raw error payloads.
export const accessErrorMessages: Record<string, string> = {
  PAUSE_NOT_ALLOWED: 'Pause is not available for this membership.',
  PAUSE_LIMIT_EXCEEDED: 'The selected duration exceeds your remaining pause allowance. Refresh to see your current allowance.',
  MEMBERSHIP_ALREADY_PAUSED: 'Your membership is currently paused. Refresh to see when it resumes.',
  MEMBERSHIP_INACTIVE: 'This membership is not currently active.',
  MEMBERSHIP_NOT_FOUND: 'This membership is not available on your account.',
  INVALID_PAUSE_DATE: 'Choose future dates within the valid pause range shown.',
  PAUSE_OVERLAP: 'These dates overlap an existing pause. Choose a different period.',
  PAUSE_PREVIEW_CHANGED: 'Your membership or pause policy changed. Review the updated dates before confirming.',
  DAILY_ACCESS_ALREADY_CONSUMED: 'You have already used your FitiGo access today.',
  DAILY_ACCESS_ALREADY_USED: 'You have already used your FitiGo access today.',
  MEMBERSHIP_PAUSED: 'Your membership access is paused. Gym access is unavailable during a pause.',
  MEMBERSHIP_EXPIRED: 'Your membership has expired. View plans to continue.',
  GYM_NOT_ELIGIBLE: 'This gym is not available with your membership.',
  INVALID_QR: 'This access QR is no longer valid. Request a new QR to check your access.',
  QR_EXPIRED: 'This access QR has expired. Request a new QR to check your access.',
  PAUSE_LIMIT_REACHED: 'You have used your pause allowance for this plan.',
  PAUSE_PAST_DATE: 'You can only pause future dates.',
  PAUSE_OVER_LIMIT: 'Selected period exceeds your remaining pause allowance.',
  PLAN_UNAVAILABLE: 'This membership plan is no longer available. Refresh plans to continue.',
  PAYMENT_NOT_CONFIGURED: 'Payments are not available yet. No money has been taken.',
  ORDER_NOT_FOUND: 'This order is not available on your account.',
  IDEMPOTENCY_CONFLICT: 'This request has already been used for a different plan. Return to plans and try again.',
  PLAN_VERSION_CHANGED: 'This plan has changed. Refresh its details before trying again.',
  PLAN_CODE_EXISTS: 'A plan with this code already exists.',
  ACCOUNT_UNAVAILABLE: 'Your account is not available for this action.',
  WALLET_MVP_DISABLED: 'Test-credit membership checkout is only available in the controlled development environment.',
  INSUFFICIENT_WALLET_BALANCE: 'Your wallet does not have enough test credits. Add test credits and refresh checkout.',
  WALLET_CURRENCY_MISMATCH: 'Your wallet currency does not match this plan.',
  MEMBERSHIP_PRICE_CHANGED: 'The price or plan terms changed. Refresh checkout and review the latest price before paying.',
  MEMBERSHIP_ALREADY_ACTIVE: 'You already have an active membership covering this purchase. View your membership instead.',
  NO_ELIGIBLE_PARTNER_GYMS: 'No Multi-Gym partners are enabled yet. Please try again after a partner gym is available.'
}
function publicBusinessCode(data: unknown): string | undefined {
  if (!data || typeof data !== 'object') return undefined
  const value = data as Record<string, unknown>
  const detail = value.detail && typeof value.detail === 'object' ? value.detail as Record<string, unknown> : null
  const candidates = [value.code, value.status, value.detail, detail?.code, detail?.status]
  return candidates.find((code): code is string => typeof code === 'string' && Object.hasOwn(accessErrorMessages, code))
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
  const requestToken = getAccessToken()
  let response: Response
  try {
    // Legacy customer endpoints fall back to a dev account for invalid tokens.
    // Fail closed by checking the strict identity endpoint before accessing them.
    if (/^\/(cart|wallet|profile|customer)(\/|\?|$)/.test(path)) {
      if (!getAccessToken()) throw new ApiError('Please sign in to continue.', 401)
      const identity = await authFetch('/api/v1/users/me', { cache: 'no-store' })
      if (!identity.ok) {
        if (identity.status === 401 && requestToken === getAccessToken()) clearTokens('expired')
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
    if (response.status === 401 && requestToken === getAccessToken() && !/^\/auth\/(login|logout|email\/verify-otp|mobile\/verify-otp)/.test(path)) clearTokens('expired')
    const code = response.status !== 401 && response.status < 500 ? publicBusinessCode(data) : undefined
    throw new ApiError(code ? accessErrorMessages[code] : safeError(response.status, data && typeof data === 'object' && 'detail' in data ? data.detail : undefined), response.status, code)
  }
  if (data === null && response.status !== 204) throw new ApiError('The server returned an unexpected response. Please try again.', response.status)
  return data as T
}

export const post = <T,>(path: string, body?: unknown) => request<T>(path, { method: 'POST', ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
export const money = (value: string | number, currency = 'INR') => new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 2 }).format(Number(value))
export const localDate = (date = new Date()) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
export const dateLabel = (date: string) => new Date(date.length === 10 ? `${date}T12:00:00` : date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })