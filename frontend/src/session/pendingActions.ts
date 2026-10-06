import { customerRoute } from '../customerRoutes'
import { ownerRoute } from '../owner/routes'
import { adminRoute } from '../admin/routes'

export type ActionMetadata = Readonly<Record<string, string>>
export type ActionLocation = { pathname: string; search: string; hash: string }
type ActionDefinition = {
  resume: 'page' | 'handler'
  allowedRoles: readonly string[]
  // Allow only explicitly specified, non-sensitive entity identifiers. Do not
  // serialize forms, QR credentials, quotes, amounts or payment instructions.
  metadataKeys: readonly string[]
  matches: (location: ActionLocation, metadata: ActionMetadata) => boolean
}
const definitions = new Map<string, ActionDefinition>()
export function definePendingAction(name: string, definition: ActionDefinition) {
  if (!/^[A-Z][A-Z0-9_]{1,63}$/.test(name) || definitions.has(name)) throw new Error('Invalid or duplicate pending action definition')
  definitions.set(name, definition)
}
export function validatePendingAction(action: unknown, metadata: unknown, location: ActionLocation) {
  if (typeof action !== 'string') return null
  const definition = definitions.get(action)
  if (!definition || !metadata || typeof metadata !== 'object' || Array.isArray(metadata)) return null
  const record = metadata as Record<string, unknown>
  if (Object.keys(record).some(key => !definition.metadataKeys.includes(key))) return null
  const safe: Record<string, string> = {}
  for (const key of definition.metadataKeys) {
    const value = record[key]
    if (typeof value !== 'string' || !/^[1-9]\d{0,15}$/.test(value) || !Number.isSafeInteger(Number(value))) return null
    safe[key] = value
  }
  if (!definition.matches(location, safe)) return null
  return { action, metadata: safe }
}
export function canResumeAction(action: string, roles: string[]) {
  return definitions.get(action)?.allowedRoles.some(role => roles.includes(role)) === true
}
export function requiresActionHandler(action: string) { return definitions.get(action)?.resume === 'handler' }
const customerRoles = ['CUSTOMER', 'USER']
definePendingAction('BOOK_VISIT', {
  resume: 'handler',
  allowedRoles: customerRoles, metadataKeys: ['gymId'],
  matches: ({ pathname }, metadata) => {
    const route = customerRoute(pathname)
    return (route.page === 'gym' || route.page === 'confirmVisit') && route.id === Number(metadata.gymId)
  }
})
definePendingAction('ADD_TO_CART', {
  resume: 'handler',
  allowedRoles: customerRoles, metadataKeys: ['gymId'],
  matches: ({ pathname }, metadata) => { const route = customerRoute(pathname); return route.page === 'bookingSchedule' && route.id === Number(metadata.gymId) }
})
// These are route/UI continuations, not commands that bypass backend actions.
definePendingAction('VIEW_MEMBERSHIP', {
  resume: 'page',
  allowedRoles: customerRoles, metadataKeys: ['membershipId'],
  matches: ({ pathname }, metadata) => { const route = customerRoute(pathname); return (route.page === 'membershipRecord' || route.page === 'membershipDetails') && route.id === Number(metadata.membershipId) }
})
definePendingAction('EDIT_GYM', {
  resume: 'page',
  allowedRoles: ['GYM_OWNER'], metadataKeys: ['gymId'],
  matches: ({ pathname }, metadata) => { const route = ownerRoute(pathname); return route.page === 'gymForm' && route.gymId === Number(metadata.gymId) }
})
definePendingAction('VIEW_REPORT', {
  resume: 'page',
  allowedRoles: ['GYM_OWNER', 'ADMIN', 'SUPER_ADMIN'], metadataKeys: [],
  matches: ({ pathname }) => ['revenue', 'analytics'].includes(ownerRoute(pathname).page) || adminRoute(pathname).page === 'reports'
})
definePendingAction('EDIT_PROFILE', {
  resume: 'page',
  allowedRoles: [...customerRoles, 'GYM_OWNER', 'GYM_STAFF', 'ADMIN', 'SUPER_ADMIN'], metadataKeys: [],
  matches: ({ pathname }) => customerRoute(pathname).page === 'settings' || ownerRoute(pathname).page === 'settings' || adminRoute(pathname).page === 'profile'
})
// PAYMENT / CHECK_IN / destructive actions deliberately have no automatic handler.
// Their route can resume, but confirmation/QR scanning must be initiated again.