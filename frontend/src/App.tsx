import { lazy, Suspense, useEffect, useState } from 'react'
import AuthModal from './components/AuthModal/AuthModal'
import { navigate, parseRoute, subscribeNavigation, type RouteState } from './router'
import { clearTokens, setTokens } from './auth'
import { subscribeOpenAuthModal } from './authUi'
import CustomerApp from './pages/CustomerApp'
import { safeReturnTo } from './customerRoutes'
import { EmptyState, Link, Skeleton } from './components/common/UI'

const OwnerApp = lazy(() => import('./owner/OwnerApp'))
const AdminApp = lazy(() => import('./admin/AdminApp'))

export default function App() {
  const [authOpen, setAuthOpen] = useState(false)

  const [route, setRoute] = useState<RouteState>(() => parseRoute(window.location.pathname))

  // Optional: preserve intent for post-login return-to-action behavior.
  const [loginIntent, setLoginIntent] = useState<string | null>(null)


  useEffect(() => {
    return subscribeOpenAuthModal((intent) => {
      setLoginIntent(intent)
      setAuthOpen(true)
    })
  }, [])

  useEffect(() => {
    return subscribeNavigation(() => setRoute(parseRoute(window.location.pathname)))
  }, [])

  return (
    <div className="appShell">
      <Suspense fallback={<div className="fg-app fg-main"><Skeleton /></div>}>
      {!/^\/(owner|admin)(\/|$)/.test(window.location.pathname) ? (
        <CustomerApp key={window.location.pathname + window.location.search} path={window.location.pathname} />
      ) : /^\/owner(\/|$)/.test(window.location.pathname) ? (
        <OwnerApp path={window.location.pathname} />
      ) : /^\/admin(\/|$)/.test(window.location.pathname) ? (
        <AdminApp path={window.location.pathname} />
      ) : (
        <div className="fg-app fg-main"><EmptyState title="Page not found" action={<Link to="/home" className="fg-button fg-button--primary">Customer home</Link>} /></div>
      )}
      </Suspense>

      <AuthModal
        open={authOpen}
        onClose={() => setAuthOpen(false)}
        onAuthed={(payload) => {
          setTokens(payload.access_token, payload.refresh_token)
          setAuthOpen(false)
          if (loginIntent?.startsWith('/')) navigate(safeReturnTo(loginIntent))
          setLoginIntent(null)
        }}
        intent={loginIntent}
      />
    </div>
  )
}

export function logout() {
  clearTokens()
}
