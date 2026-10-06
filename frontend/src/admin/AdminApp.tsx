import { lazy, Suspense } from 'react'
import { adminRoute, type AdminRoute } from './routes'
import { useIdentity } from '../session/SessionGuard'
import AdminLayout from './AdminLayout'
import { EmptyState, Link, Skeleton, ToastProvider } from './UI'
import '../customer.css'
import './admin.css'

const Login = lazy(() => import('./Login'))
const Dashboard = lazy(() => import('./Dashboard'))
const Users = lazy(() => import('./Users'))
const Gyms = lazy(() => import('./Gyms'))
const Bookings = lazy(() => import('./Bookings'))
const Account = lazy(() => import('./Account'))
const MembershipPlans = lazy(() => import('./MembershipPlans'))
export default function AdminApp({ path }: { path: string }) {
  const route = adminRoute(path)
  return <div className="fg-app ad-app"><ToastProvider><Suspense fallback={<div className="ad-loading"><Skeleton /></div>}>{route.page === 'login' ? <Login /> : route.page === 'access-denied' ? <SystemPage denied /> : route.page === 'session-expired' ? <SystemPage /> : <Authenticated path={path} route={route} />}</Suspense></ToastProvider></div>
}
function SystemPage({ denied = false }: { denied?: boolean }) {
  return <div className="ad-system"><EmptyState title={denied ? 'Access denied' : 'Your session has expired.'} description={denied ? "You don't have permission to access the FitiGo Admin Portal." : 'Please sign in again to continue securely.'} action={<Link className="fg-button fg-button--primary" to="/admin/login">{denied ? 'Return to Login' : 'Sign In'}</Link>} /></div>
}
function Authenticated({ path, route }: { path: string; route: AdminRoute }) {
  const { user, roles } = useIdentity()
  let content
  if (route.page === 'dashboard') content = <Dashboard />
  else if (route.page === 'users' || route.page === 'user') content = <Users id={route.id} />
  else if (['gyms', 'gym', 'review'].includes(route.page)) content = <Gyms id={route.id} review={route.page === 'review'} />
  else if (route.page === 'bookings' || route.page === 'booking') content = <Bookings id={route.id} />
  else if (['membership-plans', 'plan-new', 'plan-edit', 'plan-offer'].includes(route.page)) content = <MembershipPlans id={route.id} create={route.page === 'plan-new'} offer={route.page === 'plan-offer'} />
  else content = <Account page={route.page} user={user} roles={roles} />
  return <AdminLayout path={path} user={user} roles={roles}><Suspense fallback={<Skeleton />}><div key={`${route.page}:${route.id || ''}`}>{content}</div></Suspense></AdminLayout>
}