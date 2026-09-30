import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react'
import CustomerShell from '../components/navigation/CustomerShell'
import { getAccessToken, subscribeAuth } from '../auth'
import { openAuthModal } from '../authUi'
import { customerRoute, isProtectedRoute, safeReturnTo } from '../customerRoutes'
import { useResource } from '../hooks/useResource'
import { profileService } from '../services/accountService'
import { Button, EmptyState, ErrorState, Link, Skeleton } from '../components/common/UI'

const DiscoveryPage = lazy(() => import('./discovery/DiscoveryPage'))
const LocationPage = lazy(() => import('./discovery/LocationPage'))
const GymPage = lazy(() => import('./discovery/GymPage'))
const BookingPage = lazy(() => import('./booking/BookingPage'))
const CartPage = lazy(() => import('./booking/CartPage'))
const WalletPage = lazy(() => import('./wallet/WalletPage'))
const BookingsPage = lazy(() => import('./booking/BookingsPage'))
const BookingDetailPage = lazy(() => import('./booking/BookingDetailPage'))
const MyMembershipPage = lazy(() => import('./membership/MembershipPage'))
const MembershipPlansPage = lazy(() => import('./membership/MembershipPage').then(module => ({ default: module.MembershipPlansPage })))
const ProfilePage = lazy(() => import('./profile/ProfilePage'))
const SettingsPage = lazy(() => import('./profile/ProfilePage').then(module => ({ default: module.SettingsPage })))
const AccessPage = lazy(() => import('./access/AccessPage'))
const ReviewPage = lazy(() => import('./reviews/ReviewPage'))
const StaffPage = lazy(() => import('./staff/StaffPage'))

function VerifiedSession({ children }: { children: ReactNode }) {
  const session = useResource(profileService.me, 'session')
  if (session.loading) return <Skeleton cards={2} />
  if (session.error) return <ErrorState message={session.error} retry={session.retry} />
  return <>{children}</>
}
function SignIn({ path, authPage = false }: { path: string; authPage?: boolean }) {
  const intent = authPage ? safeReturnTo(new URLSearchParams(window.location.search).get('returnTo')) : path + window.location.search
  useEffect(() => { if (!authPage) return; const timer = window.setTimeout(() => openAuthModal(intent), 0); return () => window.clearTimeout(timer) }, [authPage, intent])
  return <div className="fg-narrow"><EmptyState title={authPage ? 'Welcome to FitiGo' : 'Sign in to continue'} description="Your next workout is waiting. Sign in to access bookings, memberships, and your wallet." action={<Button onClick={() => openAuthModal(intent)}>Sign in / Create account</Button>} /><Link to="/explore" className="fg-inline-link">Keep exploring gyms</Link></div>
}
export default function CustomerApp({ path }: { path: string }) {
  const [token, setToken] = useState(getAccessToken())
  useEffect(() => subscribeAuth(() => setToken(getAccessToken())), [])
  const route = customerRoute(path)
  let page: ReactNode
  switch (route.page) {
    case 'home': page = <DiscoveryPage home />; break
    case 'explore': page = <DiscoveryPage />; break
    case 'location': page = <LocationPage />; break
    case 'gym': page = <GymPage gymId={route.id} />; break
    case 'bookingAccess': case 'bookingSchedule': page = <BookingPage gymId={route.id} schedule={route.page === 'bookingSchedule'} />; break
    case 'cart': case 'checkout': page = <CartPage checkout={route.page === 'checkout'} />; break
    case 'wallet': case 'recharge': page = <WalletPage recharge={route.page === 'recharge'} />; break
    case 'bookings': case 'visits': case 'history': case 'reviews': page = <BookingsPage history={route.page === 'visits'} checkins={route.page === 'history'} reviews={route.page === 'reviews'} />; break
    case 'bookingDetail': case 'bookingSuccess': page = <BookingDetailPage id={route.id} success={route.page === 'bookingSuccess'} />; break
    case 'plans': page = <MembershipPlansPage gymId={route.id} />; break
    case 'membershipCheckout': {
      const gymId = Number(new URLSearchParams(window.location.search).get('gymId'))
      page = Number.isSafeInteger(gymId) && gymId > 0 ? <MembershipPlansPage gymId={gymId} checkout /> : <EmptyState title="Choose a membership first" action={<Link to="/explore" className="fg-button fg-button--primary">Explore gyms</Link>} />; break
    }
    case 'membership': case 'membershipSuccess': page = <MyMembershipPage success={route.page === 'membershipSuccess'} />; break
    case 'profile': page = <ProfilePage />; break
    case 'settings': page = <SettingsPage />; break
    case 'access': case 'calendar': page = <AccessPage calendar={route.page === 'calendar'} />; break
    case 'review': page = <ReviewPage id={route.id} />; break
    case 'auth': page = <SignIn path={path} authPage />; break
    case 'staff': page = <StaffPage />; break
    default: page = <EmptyState title="This page took a wrong turn" description="Let’s get you back to your next workout." action={<Link to="/home" className="fg-button fg-button--primary">Back to home</Link>} />
  }
  const content = <Suspense fallback={<Skeleton cards={3} />}>{isProtectedRoute(route) ? token ? <VerifiedSession key={token}>{page}</VerifiedSession> : <SignIn path={path} /> : page}</Suspense>
  if (route.page === 'staff') return <div className="fg-app"><main className="fg-main">{content}</main></div>
  return <CustomerShell path={path}>{content}</CustomerShell>
}