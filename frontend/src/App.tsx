import { lazy, Suspense, useEffect, useState } from 'react'
import AuthModal from './components/AuthModal/AuthModal'
import { subscribeNavigation } from './router'
import { subscribeOpenAuthModal } from './authUi'
import CustomerApp from './pages/CustomerApp'
import { Skeleton } from './components/common/UI'
import { SessionGuard, SessionProvider, useSession } from './session/SessionGuard'
import { completeLogin, logoutSession } from './session/store'

const OwnerApp = lazy(() => import('./owner/OwnerApp'))
const AdminApp = lazy(() => import('./admin/AdminApp'))

export default function App() {
  return <SessionProvider><Application /></SessionProvider>
}
function Application() {
  const [authOpen, setAuthOpen] = useState(false)
  const [location, setLocation] = useState(() => window.location.pathname + window.location.search + window.location.hash)
  const path = location.split(/[?#]/)[0]
  const session = useSession()
  useEffect(() => { if (session.status !== 'anonymous' && session.status !== 'expired') setAuthOpen(false) }, [session.status])

  useEffect(() => {
    return subscribeOpenAuthModal(() => {
      setAuthOpen(true)
    })
  }, [])

  useEffect(() => {
    return subscribeNavigation(() => setLocation(window.location.pathname + window.location.search + window.location.hash))
  }, [])

  return (
    <div className="appShell">
      <SessionGuard path={path}>
      <Suspense fallback={<div className="fg-app fg-main"><Skeleton /></div>}>
      {!/^\/(owner|admin)(\/|$)/.test(path) ? (
        <CustomerApp key={location.split('#')[0]} path={path} />
      ) : /^\/owner(\/|$)/.test(path) ? (
        <OwnerApp path={path} />
      ) : (
        <AdminApp path={path} />
      )}
      </Suspense>

      <AuthModal
        open={authOpen}
        onClose={() => setAuthOpen(false)}
        onAuthed={(payload) => {
          setAuthOpen(false)
          void completeLogin(payload)
        }}
      />
      </SessionGuard>
    </div>
  )
}

export function logout() {
  void logoutSession()
}
