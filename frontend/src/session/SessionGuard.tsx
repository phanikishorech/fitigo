import { useEffect, useSyncExternalStore, type ReactNode } from 'react'
import { Button, EmptyState, Skeleton } from '../components/common/UI'
import { navigate } from '../router'
import { canOpen, roleHome, routePolicy } from './policy'
import { getSession, logoutSession, restoreSession, startSessionTracking, subscribeSession } from './store'
import { clearReturnIntent, consumeReturnIntent, currentLocation, getReturnIntent, handlePostLoginRedirect, importLoginReturnParameter, locationUrl, requestAuthentication } from './returnIntent'
import { requiresActionHandler } from './pendingActions'

export function useSession() { return useSyncExternalStore(subscribeSession, getSession, getSession) }
export function SessionProvider({ children }: { children: ReactNode }) {
  useEffect(startSessionTracking, [])
  return <>{children}</>
}
export function useIdentity() {
  const session = useSession()
  if (session.status !== 'authenticated') throw new Error('Verified session is required')
  return session.identity
}
function Redirect({ to }: { to: string }) {
  const from = window.location.pathname + window.location.search
  useEffect(() => {
    // Do not overwrite a newer navigation (e.g. password-change success or logout).
    if (window.location.pathname + window.location.search === from) navigate(to, true)
  }, [to, from])
  return <div className="fg-app fg-main"><Skeleton cards={1} /></div>
}
function LoginRequired({ expired }: { expired: boolean }) {
  const from = locationUrl(currentLocation())
  useEffect(() => { if (locationUrl(currentLocation()) === from) requestAuthentication({}, expired) }, [from, expired])
  return <div className="fg-app fg-main"><Skeleton cards={1} /></div>
}
function PostLogin({ identity }: { identity: { user: { id: number }; roles: string[] } }) {
  const from = locationUrl(currentLocation())
  useEffect(() => { if (locationUrl(currentLocation()) === from) handlePostLoginRedirect(identity) }, [identity, from])
  return <div className="fg-app fg-main"><Skeleton cards={1} /></div>
}
function ReturnCompletion() {
  const session = useSession()
  const location = locationUrl(currentLocation())
  useEffect(() => {
    if (session.status !== 'authenticated') return
    const intent = getReturnIntent()
    if (!intent || intent.phase !== 'returning') return
    if (locationUrl(intent) !== location) { clearReturnIntent(intent.id); return }
    // Allow lazy routes and resource loading to finish before consuming a page
    // continuation. Handler actions are claimed by usePendingAction instead.
    let timer: ReturnType<typeof setTimeout>
    let stopped = false
    const finish = () => {
      if (stopped || locationUrl(currentLocation()) !== location) return
      if (document.querySelector('[aria-label="Loading"]')) { timer = setTimeout(finish, 100); return }
      if (intent.hash) {
        try { document.getElementById(decodeURIComponent(intent.hash.slice(1)))?.scrollIntoView({ block: 'start' }) } catch { /* non-anchor fragment */ }
      }
      if (!intent.action || !requiresActionHandler(intent.action)) consumeReturnIntent(intent.id, session.identity)
    }
    timer = setTimeout(finish, 0)
    return () => { stopped = true; clearTimeout(timer) }
  }, [session, location])
  return null
}
export function SessionGuard({ path, children }: { path: string; children: ReactNode }) {
  const session = useSession(); const policy = routePolicy(path)
  useEffect(() => { if (policy.login) importLoginReturnParameter() }, [path, policy.login])
  // A synchronous auth event can render before the navigation subscriber commits
  // its new path. Never redirect using that previous route's policy.
  if (path !== window.location.pathname) return <div className="fg-app fg-main"><Skeleton cards={1} /></div>
  if (session.status === 'loading') return <div className="fg-app fg-main"><Skeleton cards={2} /></div>
  if (session.status === 'error') return <div className="fg-app fg-main"><EmptyState title="Unable to verify your session" description={session.message} action={<><Button onClick={() => void restoreSession()}>Try Again</Button><Button variant="secondary" onClick={() => void logoutSession()}>Sign out</Button></>} /></div>
  if (session.status === 'invalid-role' || session.status === 'forbidden') return <div className="fg-app fg-main"><EmptyState title="Access denied" description={session.status === 'invalid-role' ? 'Your account has no supported role. Contact the FitiGo administrator.' : 'Your account is not permitted to access FitiGo.'} action={<><Button onClick={() => void restoreSession()}>Check again</Button><Button variant="secondary" onClick={() => void logoutSession()}>Sign out</Button></>} /></div>
  if (session.status === 'authenticated') {
    if (policy.login) return <PostLogin identity={session.identity} />
    if (!canOpen(session.identity.roles, path)) return <Redirect to={roleHome(session.identity.roles)!} />
  } else {
    if (policy.protected || (session.status === 'expired' && policy.portal)) return <LoginRequired expired={session.status === 'expired'} />
    if (policy.login && session.status === 'expired' && !window.location.search.includes('expired=1')) return <Redirect to="/login?expired=1" />
  }
  return <>{children}<ReturnCompletion /></>
}