import { customerRoute, isProtectedRoute } from '../customerRoutes'
import { ownerRoute } from '../owner/routes'
import { adminRoute } from '../admin/routes'

export type Portal = 'customer' | 'owner' | 'admin'
const supported = ['CUSTOMER', 'USER', 'GYM_OWNER', 'GYM_STAFF', 'ADMIN', 'SUPER_ADMIN']
export function backendRoles(value: unknown): string[] | null {
  if (!Array.isArray(value) || !value.length || value.some(role => typeof role !== 'string' || !supported.includes(role))) return null
  return [...new Set(value)]
}
export function hasPortal(roles: string[], portal: Portal) {
  return roles.some(role => portalRoles[portal].includes(role))
}
const portalRoles: Record<Portal, string[]> = { customer: ['CUSTOMER', 'USER'], owner: ['GYM_OWNER', 'GYM_STAFF'], admin: ['ADMIN', 'SUPER_ADMIN'] }
export function roleHome(roles: string[]) {
  // Multi-role home precedence only; permissions always retain the backend roles.
  if (hasPortal(roles, 'admin')) return '/admin/dashboard'
  if (hasPortal(roles, 'owner')) return '/owner/dashboard'
  if (hasPortal(roles, 'customer')) return '/home'
  return null
}
function basePolicy(path: string): { portal: Portal | null; protected: boolean; login?: boolean; staffAllowed?: boolean } {
  const clean = path.replace(/\/+$/, '') || '/'
  if (['/login', '/auth', '/auth/login', '/auth/otp', '/owner/login', '/admin/login'].includes(clean)) return { portal: null, protected: false, login: true }
  if (['/auth/forgot-password', '/auth/reset-password', '/owner/register', '/owner/verify', '/admin/access-denied', '/admin/session-expired'].includes(clean)) return { portal: null, protected: false }
  if (/^\/admin(\/|$)/.test(clean)) return { portal: 'admin', protected: true }
  if (/^\/owner(\/|$)/.test(clean)) return { portal: 'owner', protected: true, staffAllowed: ['dashboard', 'check-in', 'settings', 'notifications', 'help', 'more'].includes(ownerRoute(clean).page) }
  if (clean === '/staff/check-in') return { portal: 'owner', protected: true, staffAllowed: true }
  const route = customerRoute(clean)
  // Booking screens also require authentication. Discovery and gym previews stay public.
  return { portal: 'customer', protected: isProtectedRoute(route) || ['bookingAccess', 'bookingSchedule'].includes(route.page) }
}
export function routePolicy(path: string) {
  const policy = basePolicy(path)
  const allowedRoles = !policy.portal ? [] : policy.portal === 'owner' && policy.staffAllowed === false ? ['GYM_OWNER'] : portalRoles[policy.portal]
  return { ...policy, allowedRoles }
}
export function isReturnableRoute(path: string) {
  const policy = routePolicy(path)
  if (policy.login || !policy.portal) return false
  if (policy.portal === 'admin') return adminRoute(path).page !== 'notFound'
  if (policy.portal === 'owner') return path.replace(/\/+$/, '') === '/staff/check-in' || ownerRoute(path).page !== 'notFound'
  return customerRoute(path).page !== 'notFound'
}
export function canOpen(roles: string[], path: string) {
  const policy = routePolicy(path)
  if (!policy.portal) return true
  return roles.some(role => policy.allowedRoles.includes(role))
}