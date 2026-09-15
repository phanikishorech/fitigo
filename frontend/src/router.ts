export type RouteName =
  | 'home'
  | 'nearby'
  | 'gym'
  | 'gymAccess'
  | 'membership'
  | 'myAccess'
  | 'saved'
  | 'bookings'
  | 'profile'
  | 'settings'
  | 'classes'
  | 'checkout'
  | 'ownerLogin'
  | 'ownerRegister'
  | 'ownerDashboard'
  | 'ownerGyms'
  | 'ownerGym'
  | 'adminLogin'
  | 'adminDashboard'
  | 'adminUsers'
  | 'adminGyms'
  | 'adminBookings'

export type RouteState =
  | { name: 'home' }
  | { name: 'nearby' }
  | { name: 'gym'; gymId: number }
  | { name: 'gymAccess'; gymId: number }
  | { name: 'membership' }
  | { name: 'myAccess' }
  | { name: 'saved' }
  | { name: 'bookings' }
  | { name: 'profile' }
  | { name: 'settings' }
  | { name: 'classes' }
  | { name: 'checkout' }
  | { name: 'ownerLogin' }
  | { name: 'ownerRegister' }
  | { name: 'ownerDashboard' }
  | { name: 'ownerGyms' }
  | { name: 'ownerGym'; gymId: number }
  | { name: 'adminLogin' }
  | { name: 'adminDashboard' }
  | { name: 'adminUsers' }
  | { name: 'adminGyms' }
  | { name: 'adminBookings' }

const NAV_EVENT = 'fitigo:navigate'

export function parseRoute(pathname: string): RouteState {
  if (pathname === '/admin/login') return { name: 'adminLogin' }
  if (pathname === '/admin') return { name: 'adminDashboard' }
  if (pathname === '/admin/users') return { name: 'adminUsers' }
  if (pathname === '/admin/gyms') return { name: 'adminGyms' }
  if (pathname === '/admin/bookings') return { name: 'adminBookings' }

  if (pathname === '/owner/login') return { name: 'ownerLogin' }
  if (pathname === '/owner/register') return { name: 'ownerRegister' }
  if (pathname === '/owner') return { name: 'ownerDashboard' }
  if (pathname === '/owner/gyms') return { name: 'ownerGyms' }

  const og = pathname.match(/^\/owner\/gyms\/(\d+)\/?$/)
  if (og) return { name: 'ownerGym', gymId: Number(og[1]) }

  if (pathname === '/membership') return { name: 'membership' }
  if (pathname === '/classes') return { name: 'classes' }
  if (pathname === '/checkout') return { name: 'checkout' }
  if (pathname === '/my-access') return { name: 'myAccess' }
  if (pathname === '/saved') return { name: 'saved' }
  if (pathname === '/bookings') return { name: 'bookings' }
  if (pathname === '/profile') return { name: 'profile' }
  if (pathname === '/settings') return { name: 'settings' }

  if (pathname.startsWith('/nearby')) return { name: 'nearby' }

  const m2 = pathname.match(/^\/gyms\/(\d+)\/access\/?$/)
  if (m2) return { name: 'gymAccess', gymId: Number(m2[1]) }

  const m = pathname.match(/^\/gyms\/(\d+)\/?$/)
  if (m) return { name: 'gym', gymId: Number(m[1]) }

  return { name: 'home' }
}

export function scrollToId(id: string) {
  const el = document.getElementById(id)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

export function navigate(to: string) {
  const cur = `${window.location.pathname}${window.location.search}${window.location.hash}`
  if (cur === to) return
  window.history.pushState({}, '', to)
  window.dispatchEvent(new CustomEvent(NAV_EVENT, { detail: { to } }))
}

export function subscribeNavigation(handler: () => void) {
  const onNav = () => handler()
  const onPop = () => handler()
  window.addEventListener(NAV_EVENT, onNav as EventListener)
  window.addEventListener('popstate', onPop)
  return () => {
    window.removeEventListener(NAV_EVENT, onNav as EventListener)
    window.removeEventListener('popstate', onPop)
  }
}
