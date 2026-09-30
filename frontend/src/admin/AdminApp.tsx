import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { getAccessToken, subscribeAuth } from '../auth'
import { navigate } from '../router'
import { adminRoute, type AdminRoute } from './routes'
import { adminAuthService, adminError } from './services'
import { ApiError } from '../services/client'
import { useResource } from '../hooks/useResource'
import AdminLayout from './AdminLayout'
import { Button, EmptyState, Link, Skeleton, ToastProvider } from './UI'
import '../customer.css'
import './admin.css'

const Login = lazy(() => import('./Login'))
const Dashboard = lazy(() => import('./Dashboard'))
const Users = lazy(() => import('./Users'))
const Gyms = lazy(() => import('./Gyms'))
const Bookings = lazy(() => import('./Bookings'))
const Account = lazy(() => import('./Account'))
export default function AdminApp({ path }: { path: string }) {
  const route = adminRoute(path)
  const [token, setToken] = useState(getAccessToken)
  const hadSession = useRef(!!token)
  useEffect(() => subscribeAuth(() => { const next = getAccessToken(); if (next) hadSession.current = true; setToken(next) }), [])
  useEffect(() => {
    if (!token && !['login', 'access-denied', 'session-expired'].includes(route.page)) navigate(hadSession.current ? '/admin/session-expired' : `/admin/login?returnTo=${encodeURIComponent(path + window.location.search)}`)
  }, [token, path])
  return <div className="fg-app ad-app"><ToastProvider><Suspense fallback={<div className="ad-loading"><Skeleton /></div>}>{route.page === 'login' ? <Login /> : route.page === 'access-denied' ? <SystemPage denied /> : route.page === 'session-expired' ? <SystemPage /> : token ? <Authenticated key={token} path={path} route={route} /> : <div className="ad-loading"><Skeleton /></div>}</Suspense></ToastProvider></div>
}
function SystemPage({ denied = false }: { denied?: boolean }) {
  return <div className="ad-system"><EmptyState title={denied ? 'Access denied' : 'Your session has expired.'} description={denied ? "You don't have permission to access the FitiGo Admin Portal." : 'Please sign in again to continue securely.'} action={<Link className="fg-button fg-button--primary" to="/admin/login">{denied ? 'Return to Login' : 'Sign In'}</Link>} /></div>
}
function Authenticated({ path, route }: { path: string; route: AdminRoute }) {
  const identity = useResource(async () => {
    try { return await adminAuthService.identity() } catch (error) {
      if (error instanceof ApiError && error.status === 403) navigate('/admin/access-denied')
      throw new Error(adminError(error))
    }
  }, 'admin-identity')
  if (identity.loading) return <div className="ad-loading"><Skeleton /></div>
  if (identity.error) return <div className="ad-system"><EmptyState title="Unable to verify your session" description={identity.error} action={<><Button onClick={identity.retry}>Try again</Button><Link to="/admin/login">Return to Login</Link></>} /></div>
  const { user, roles } = identity.data!
  let content
  if (route.page === 'dashboard') content = <Dashboard />
  else if (route.page === 'users' || route.page === 'user') content = <Users id={route.id} />
  else if (['gyms', 'gym', 'review'].includes(route.page)) content = <Gyms id={route.id} review={route.page === 'review'} />
  else if (route.page === 'bookings' || route.page === 'booking') content = <Bookings id={route.id} />
  else content = <Account page={route.page} user={user} roles={roles} />
  return <AdminLayout path={path} user={user} roles={roles}><Suspense fallback={<Skeleton />}><div key={`${route.page}:${route.id || ''}`}>{content}</div></Suspense></AdminLayout>
}