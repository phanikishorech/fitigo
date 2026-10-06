import { lazy, Suspense } from 'react'
import { useIdentity } from '../session/SessionGuard'
import { ownerRoute, type OwnerRoute } from './routes'
import { OwnerProvider, useOwner } from './context'
import OwnerLayout from './OwnerLayout'
import { EmptyState, ErrorState, Link, Skeleton } from './UI'
import '../customer.css'
import './owner.css'

const AuthPage = lazy(() => import('./AuthPage'))
const Dashboard = lazy(() => import('./Dashboard'))
const Gyms = lazy(() => import('./Gyms'))
const Bookings = lazy(() => import('./Bookings'))
const Operations = lazy(() => import('./Operations'))
const CheckIn = lazy(() => import('./CheckIn'))
const Account = lazy(() => import('./Account'))

export default function OwnerApp({ path }: { path: string }) {
  const route = ownerRoute(path)
  const auth = ['login', 'register', 'verify'].includes(route.page)
  return <div className="fg-app ow-app"><Suspense fallback={<div className="ow-loading"><Skeleton /></div>}>{auth ? <AuthPage key={route.page} page={route.page} /> : <Authenticated path={path} route={route} />}</Suspense></div>
}
function Authenticated({ path, route }: { path: string; route: OwnerRoute }) {
  const { user, roles } = useIdentity()
  return <OwnerProvider user={user} roles={roles} routeGymId={route.gymId}><OwnerLayout path={path}><Content route={route} /></OwnerLayout></OwnerProvider>
}
function Content({ route }: { route: OwnerRoute }) {
  const { loading, error, refreshGyms, gymId, roles, gyms } = useOwner()
  if (loading) return <Skeleton />
  if (error) return <ErrorState message={error} retry={refreshGyms} />
  if (route.gymId && !gyms.some(g => g.id === route.gymId)) return <EmptyState title="Gym unavailable" description="This gym is not associated with your account." action={<Link to="/owner/gyms">View your gyms</Link>} />
  const owner = roles.includes('GYM_OWNER')
  if (!owner && !['check-in', 'settings', 'notifications', 'help', 'more'].includes(route.page)) return <EmptyState title="Staff workspace" description="Your role provides check-in access for assigned gyms." action={<Link to="/owner/check-in" className="fg-button fg-button--primary">Open check-in</Link>} />
  let content
  if (route.page === 'dashboard') content = <Dashboard />
  else if (['gyms', 'gym', 'gymForm'].includes(route.page)) content = <Gyms gymId={route.gymId} form={route.page === 'gymForm'} />
  else if (route.page === 'bookings' || route.page === 'bookingsDetail') content = <Bookings id={route.id} />
  else if (['memberships', 'classes', 'slots', 'staff', 'staffForm', 'staffDetail'].includes(route.page)) content = <Operations route={route} />
  else if (route.page === 'check-in') content = <CheckIn />
  else content = <Account page={route.page} />
  return <Suspense fallback={<Skeleton />}><div key={`${route.page}:${route.id || ''}:${route.mode || ''}:${route.gymId || (route.page === 'gymForm' || route.page === 'bookingsDetail' ? '' : gymId) || ''}`}>{content}</div></Suspense>
}