export type CustomerRoute =
  | { page: 'home' | 'explore' | 'location' | 'cart' | 'checkout' | 'wallet' | 'recharge' | 'bookings' | 'membership' | 'membershipCheckout' | 'membershipSuccess' | 'profile' | 'access' | 'calendar' | 'history' | 'visits' | 'reviews' | 'settings' | 'auth' | 'staff' | 'notFound' }
  | { page: 'gym' | 'bookingAccess' | 'bookingSchedule' | 'plans' | 'bookingDetail' | 'bookingSuccess' | 'review' | 'membershipRecord' | 'membershipDetails' | 'confirmVisit'; id: number }
  | { page: 'membershipPause' | 'membershipGyms' | 'multiGymPlans' }

export function customerRoute(path: string): CustomerRoute {
  const normalized = path.replace(/\/+$/, '') || '/'
  const aliases: Record<string, CustomerRoute['page']> = {
    '/': 'home', '/home': 'home', '/explore': 'explore', '/explore/search': 'explore', '/nearby': 'explore', '/classes': 'explore',
    '/location': 'location', '/cart': 'cart', '/checkout': 'checkout', '/wallet': 'wallet', '/wallet/recharge': 'recharge',
    '/bookings': 'bookings', '/membership': 'membership', '/profile/membership': 'membership',
    '/gyms': 'membershipGyms', '/membership/gyms': 'membershipGyms', '/membership/pause': 'membershipPause',
    '/membership/multi-gym/plans': 'multiGymPlans',
    '/membership/checkout': 'membershipCheckout', '/membership/success': 'membershipSuccess', '/profile': 'profile',
    '/access/qr': 'access', '/my-access': 'access', '/profile/access/today': 'access', '/profile/access': 'calendar',
    '/profile/history': 'history', '/profile/visits': 'visits', '/profile/reviews': 'reviews', '/settings': 'settings',
    '/auth': 'auth', '/auth/login': 'auth', '/auth/otp': 'auth', '/auth/profile-setup': 'settings', '/staff/check-in': 'staff'
  }
  if (aliases[normalized]) return { page: aliases[normalized] } as CustomerRoute
  const patterns: [RegExp, 'gym' | 'bookingAccess' | 'bookingSchedule' | 'plans' | 'bookingDetail' | 'bookingSuccess' | 'review' | 'membershipRecord' | 'membershipDetails' | 'confirmVisit'][] = [
    [/^\/membership\/(\d+)$/, 'membershipRecord'], [/^\/membership\/(\d+)\/details$/, 'membershipDetails'], [/^\/gyms\/(\d+)\/visit$/, 'confirmVisit'],
    [/^\/gyms\/(\d+)$/, 'gym'], [/^\/gyms\/(\d+)\/(?:access|book\/access)$/, 'bookingAccess'],
    [/^\/gyms\/(\d+)\/book\/schedule$/, 'bookingSchedule'], [/^\/gyms\/(\d+)\/membership$/, 'plans'],
    [/^\/bookings?\/(\d+)$/, 'bookingDetail'], [/^\/booking\/(\d+)\/success$/, 'bookingSuccess'], [/^\/reviews\/(\d+)$/, 'review']
  ]
  for (const [pattern, page] of patterns) { const match = normalized.match(pattern); if (match && Number.isSafeInteger(Number(match[1])) && Number(match[1]) > 0) return { page, id: Number(match[1]) } }
  return { page: 'notFound' }
}
export function isProtectedRoute(route: CustomerRoute) {
  return !['home', 'explore', 'location', 'gym', 'bookingAccess', 'bookingSchedule', 'plans', 'auth', 'notFound'].includes(route.page)
}
export function safeReturnTo(value: string | null | undefined) {
  if (!value || !value.startsWith('/') || value.startsWith('//') || /[\\\r\n]/.test(value)) return '/home'
  const route = customerRoute(value.split(/[?#]/)[0])
  return ['auth', 'notFound', 'staff'].includes(route.page) ? '/home' : value
}