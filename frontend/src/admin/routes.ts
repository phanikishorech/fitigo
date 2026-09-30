export type AdminRoute = { page: 'login' | 'access-denied' | 'session-expired' | 'dashboard' | 'users' | 'user' | 'gyms' | 'gym' | 'review' | 'bookings' | 'booking' | 'reports' | 'notifications' | 'profile' | 'settings' | 'audit-logs' | 'notFound'; id?: number }
export function adminRoute(path: string): AdminRoute {
  const normalized = path.replace(/\/+$/, '')
  if (normalized === '/admin') return { page: 'dashboard' }
  const pages = ['login', 'access-denied', 'session-expired', 'dashboard', 'users', 'gyms', 'bookings', 'reports', 'notifications', 'profile', 'settings', 'audit-logs'] as const
  for (const page of pages) if (normalized === `/admin/${page}`) return { page }
  const match = normalized.match(/^\/admin\/(users|gyms|bookings)\/(\d+)(\/review)?$/)
  if (match && Number.isSafeInteger(Number(match[2])) && Number(match[2]) > 0 && (!match[3] || match[1] === 'gyms')) return { page: match[3] ? 'review' : match[1] === 'users' ? 'user' : match[1] === 'gyms' ? 'gym' : 'booking', id: Number(match[2]) }
  return { page: 'notFound' }
}
export function adminReturnTo(value: string | null) {
  if (!value || !value.startsWith('/admin/')) return '/admin/dashboard'
  const route = adminRoute(value.split('?')[0])
  return ['login', 'access-denied', 'session-expired', 'notFound'].includes(route.page) ? '/admin/dashboard' : value
}