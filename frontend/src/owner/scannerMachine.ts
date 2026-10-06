import type { CheckInResult } from './services'

export const RESULT_DISPLAY_MS = 2000
export const DUPLICATE_COOLDOWN_MS = 2500
export const QR_REMOVAL_MS = 600
export const VALIDATION_TIMEOUT_MS = 12000
export type ScannerState = 'PERMISSION_REQUIRED' | 'CAMERA_READY' | 'SCANNING' | 'VALIDATING' | 'APPROVED' | 'REJECTED' | 'CAMERA_ERROR'
export type Approval = Extract<CheckInResult, { success: true }>
export type Rejection = { success: false; status: string; message: string }
export type ScannerError = { kind: 'camera' | 'permission' | 'verification'; message: string; code?: string }
export type ScannerContext = {
  state: ScannerState
  cameraAttached: boolean
  scanValue: string | null
  validationResult: Approval | Rejection | null
  error: ScannerError | null
  isProcessingScan: boolean
  lastScannedValue: string | null
  lastScanTimestamp: number | null
  awaitingRemoval: boolean
  absentSince: number | null
  cycle: number
  resumeState: 'SCANNING' | 'PERMISSION_REQUIRED' | 'CAMERA_ERROR'
}
export const initialScannerState: ScannerContext = {
  state: 'PERMISSION_REQUIRED', cameraAttached: false, scanValue: null, validationResult: null,
  error: null, isProcessingScan: false, lastScannedValue: null, lastScanTimestamp: null,
  awaitingRemoval: false, absentSince: null, cycle: 0, resumeState: 'PERMISSION_REQUIRED'
}
export type ScannerEvent =
  | { type: 'CAMERA_PERMISSION_GRANTED' | 'CAMERA_INITIALIZED' | 'RETRY_CAMERA' | 'SCANNER_UNMOUNTED' }
  | { type: 'CAMERA_PERMISSION_DENIED' | 'CAMERA_FAILED' | 'CAMERA_INIT_FAILED'; error: ScannerError }
  | { type: 'QR_DETECTED' | 'MANUAL_QR'; qrValue: string; at: number }
  | { type: 'FRAME_OBSERVED'; value: string | null; at: number }
  | { type: 'VALIDATION_APPROVED'; cycle: number; result: Approval; at: number }
  | { type: 'VALIDATION_REJECTED'; cycle: number; result: Rejection; at: number }
  | { type: 'VALIDATION_ERROR'; cycle: number; error: ScannerError; at: number }
  | { type: 'RESULT_TIMEOUT' | 'CLEAR_VERIFICATION_ERROR'; cycle: number }

export function mayScan(context: ScannerContext, value: string, at: number, manual = false) {
  if (!value || context.isProcessingScan || context.error?.kind === 'verification') return false
  if (context.state !== 'SCANNING' && !(manual && ['CAMERA_ERROR', 'PERMISSION_REQUIRED'].includes(context.state))) return false
  if (context.lastScannedValue === value) {
    if (!manual && context.awaitingRemoval) return false
    if (context.lastScanTimestamp !== null && at - context.lastScanTimestamp < DUPLICATE_COOLDOWN_MS) return false
  }
  return true
}

// Pure transition function: clocks, cameras, network and timers belong to the controller.
export function scannerReducer(context: ScannerContext, event: ScannerEvent): ScannerContext {
  switch (event.type) {
    case 'CAMERA_PERMISSION_GRANTED':
      if (!['PERMISSION_REQUIRED', 'CAMERA_ERROR'].includes(context.state) || context.isProcessingScan) return context
      return { ...context, state: 'CAMERA_READY', error: null, scanValue: null, validationResult: null }
    case 'RETRY_CAMERA':
      if (context.state !== 'CAMERA_ERROR' || context.isProcessingScan) return context
      return { ...context, state: 'CAMERA_READY', error: null }
    case 'CAMERA_INITIALIZED':
      if (context.state !== 'CAMERA_READY') return context
      return { ...context, state: 'SCANNING', cameraAttached: true, error: null }
    case 'CAMERA_PERMISSION_DENIED':
    case 'CAMERA_FAILED':
    case 'CAMERA_INIT_FAILED':
      return { ...context, state: event.type === 'CAMERA_PERMISSION_DENIED' ? 'PERMISSION_REQUIRED' : 'CAMERA_ERROR', cameraAttached: false, error: event.error, scanValue: null, validationResult: null, isProcessingScan: false, cycle: context.cycle + 1 }
    case 'FRAME_OBSERVED': {
      if (context.state !== 'SCANNING' || !context.awaitingRemoval) return context
      if (event.value === context.lastScannedValue) return context.absentSince === null ? context : { ...context, absentSince: null }
      // A different QR is immediately eligible; empty frames must persist briefly
      // so momentary decode misses cannot repeatedly submit a stationary QR.
      if (event.value || (context.absentSince !== null && event.at - context.absentSince >= QR_REMOVAL_MS)) return { ...context, awaitingRemoval: false, absentSince: null }
      return context.absentSince === null ? { ...context, absentSince: event.at } : context
    }
    case 'QR_DETECTED':
    case 'MANUAL_QR':
      if (!mayScan(context, event.qrValue, event.at, event.type === 'MANUAL_QR')) return context
      return { ...context, state: 'VALIDATING', scanValue: event.qrValue, validationResult: null, error: null, isProcessingScan: true, lastScannedValue: event.qrValue, lastScanTimestamp: event.at, awaitingRemoval: true, absentSince: null, cycle: context.cycle + 1, resumeState: context.cameraAttached ? 'SCANNING' : context.state === 'CAMERA_ERROR' ? 'CAMERA_ERROR' : 'PERMISSION_REQUIRED' }
    case 'VALIDATION_APPROVED':
    case 'VALIDATION_REJECTED':
      if (context.state !== 'VALIDATING' || context.cycle !== event.cycle) return context
      if (event.type === 'VALIDATION_APPROVED' && (event.result.success !== true || event.result.status !== 'CHECKED_IN')) return context
      if (event.type === 'VALIDATION_REJECTED' && event.result.success !== false) return context
      return { ...context, state: event.type === 'VALIDATION_APPROVED' ? 'APPROVED' : 'REJECTED', validationResult: event.result, scanValue: null, error: null, lastScanTimestamp: event.at }
    case 'VALIDATION_ERROR':
      if (context.state !== 'VALIDATING' || context.cycle !== event.cycle) return context
      return { ...context, state: context.cameraAttached ? 'SCANNING' : context.resumeState, scanValue: null, validationResult: null, error: event.error, isProcessingScan: false, awaitingRemoval: true, lastScanTimestamp: event.at }
    case 'RESULT_TIMEOUT':
      if (!['APPROVED', 'REJECTED'].includes(context.state) || context.cycle !== event.cycle) return context
      return { ...context, state: context.cameraAttached ? 'SCANNING' : context.resumeState, scanValue: null, validationResult: null, error: null, isProcessingScan: false }
    case 'CLEAR_VERIFICATION_ERROR':
      return event.cycle === context.cycle && context.error?.kind === 'verification' ? { ...context, error: null } : context
    case 'SCANNER_UNMOUNTED':
      return { ...initialScannerState, cycle: context.cycle + 1 }
    default:
      return context
  }
}

const rejectionMessages: Record<string, string> = {
  INVALID_QR: 'Invalid QR. Ask the member to show a current access QR.', QR_INVALID: 'Invalid QR. Ask the member to show a current access QR.',
  QR_EXPIRED: 'This QR has expired. Ask the member to generate a new QR.', QR_ALREADY_USED: 'This QR has already been used.',
  DAILY_ACCESS_ALREADY_USED: 'Today’s access has already been used.', DAILY_ACCESS_ALREADY_CONSUMED: 'Today’s access has already been used.',
  MEMBERSHIP_EXPIRED: 'Membership expired.', MEMBERSHIP_PAUSED: 'Membership access is paused.', MEMBERSHIP_INACTIVE: 'Membership is not active.',
  GYM_NOT_ELIGIBLE: 'Membership not valid at this gym.', WRONG_GYM: 'Membership not valid at this gym.', MEMBERSHIP_NOT_ELIGIBLE: 'Membership does not cover this visit.',
  GYM_NOT_ALLOWED: 'Your staff account is not assigned to this gym.', CUSTOMER_NOT_ELIGIBLE: 'Customer is not eligible for entry.'
}
// Existing endpoint collapses some business failures into INVALID_QR. Whitelist
// its exact public messages; never render arbitrary backend exception text.
const legacyMessages: Record<string, string> = {
  'Invalid or expired QR': 'Invalid or expired QR. Ask the member to generate a new QR.',
  'QR is only valid for today': 'This QR is no longer valid for today.',
  'This visit has been paused.': 'Membership access is paused.',
  'Membership is not active': 'Membership is not active.', 'No active membership': 'No active membership covers this visit.',
  'Access is not available.': 'Membership access is not available.', 'Customer is not active': 'Customer account is not active.',
  'Gym is closed': 'The gym is currently closed.', 'Outside allowed check-in window': 'Outside the allowed check-in hours.',
  "Today's gym access has already been used.": 'Today’s access has already been used.',
  "{'code': 'GYM_NOT_ELIGIBLE'}": 'Membership not valid at this gym.', 'Gym not found': 'This gym is not available for check-in.'
}
export function normalizeCheckIn(value: unknown): Approval | Rejection | null {
  if (!value || typeof value !== 'object') return null
  const data = value as Record<string, unknown>
  if (data.success === true && data.status === 'CHECKED_IN' &&
      ['customer_name', 'gym_name', 'access_type', 'checkin_time'].every(key => typeof data[key] === 'string' && !!data[key]) &&
      Number.isFinite(Date.parse(data.checkin_time as string))) return data as Approval
  if (data.success !== false || typeof data.status !== 'string' || !rejectionMessages[data.status] || typeof data.message !== 'string') return null
  return { success: false, status: data.status, message: legacyMessages[data.message] || rejectionMessages[data.status] }
}