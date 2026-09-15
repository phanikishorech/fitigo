import { useEffect, useMemo, useState } from 'react'
import AuthModal from './components/AuthModal/AuthModal'
import HomePage from './screens/Home/HomePage'
import NearbyGymsPage from './screens/NearbyGyms/NearbyGymsPage'
import GymDetailsPage from './screens/GymDetails/GymDetailsPage'
import GymAccessPage from './screens/GymAccess/GymAccessPage'
import CheckoutPage from './screens/Checkout/CheckoutPage'
import StaticPage from './screens/Static/StaticPage'
import UserProfilePage from './screens/Profile/UserProfilePage'
import MembershipSubscriptionPage from './screens/Membership/MembershipSubscriptionPage'
import GymOwnerLoginPage from './screens/GymOwner/GymOwnerLoginPage'
import GymOwnerRegisterPage from './screens/GymOwner/GymOwnerRegisterPage'
import GymOwnerDashboardPage from './screens/GymOwner/GymOwnerDashboardPage'
import GymOwnerGymPage from './screens/GymOwner/GymOwnerGymPage'
import AdminLoginPage from './screens/Admin/AdminLoginPage'
import AdminDashboardPage from './screens/Admin/AdminDashboardPage'
import AdminUsersPage from './screens/Admin/AdminUsersPage'
import AdminGymsPage from './screens/Admin/AdminGymsPage'
import AdminBookingsPage from './screens/Admin/AdminBookingsPage'
import { parseRoute, subscribeNavigation, type RouteState } from './router'
import { authFetch, clearTokens, getAccessToken, setTokens, subscribeAuth } from './auth'
import { subscribeOpenAuthModal } from './authUi'

type AuthedUser = {
  firstName: string
  email: string
}

export default function App() {
  const [authOpen, setAuthOpen] = useState(false)
  const [user, setUser] = useState<AuthedUser | null>(null)

  const [route, setRoute] = useState<RouteState>(() => parseRoute(window.location.pathname))

  // Optional: preserve intent for post-login return-to-action behavior.
  const [loginIntent, setLoginIntent] = useState<string | null>(null)

  const headerCtaText = useMemo(() => {
    if (user) return user.firstName
    return 'Login / Sign Up'
  }, [user])

  const initials = useMemo(() => {
    if (!user?.firstName) return 'M'
    return user.firstName.slice(0, 1).toUpperCase()
  }, [user?.firstName])

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'l' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        setLoginIntent('keyboard_shortcut')
        setAuthOpen(true)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  useEffect(() => {
    return subscribeOpenAuthModal((intent) => {
      setLoginIntent(intent)
      setAuthOpen(true)
    })
  }, [])

  useEffect(() => {
    return subscribeNavigation(() => setRoute(parseRoute(window.location.pathname)))
  }, [])

  useEffect(() => {
    async function loadMe() {
      const token = getAccessToken()
      if (!token) {
        setUser(null)
        return
      }
      try {
        const r = await authFetch('/api/v1/users/me')
        if (!r.ok) throw new Error('not authed')
        const me = (await r.json()) as { first_name: string | null; email: string }
        setUser({ firstName: me.first_name ?? 'Member', email: me.email })
      } catch {
        setUser(null)
      }
    }

    loadMe()
    return subscribeAuth(() => loadMe())
  }, [])

  return (
    <div className="appShell">
      {route.name === 'ownerLogin' ? (
        <GymOwnerLoginPage />
      ) : route.name === 'ownerRegister' ? (
        <GymOwnerRegisterPage />
      ) : route.name === 'ownerDashboard' ? (
        <GymOwnerDashboardPage />
      ) : route.name === 'ownerGyms' ? (
        <GymOwnerDashboardPage initialTab="gyms" />
      ) : route.name === 'ownerGym' ? (
        <GymOwnerGymPage gymId={route.gymId} />
      ) : route.name === 'adminLogin' ? (
        <AdminLoginPage />
      ) : route.name === 'adminDashboard' ? (
        <AdminDashboardPage />
      ) : route.name === 'adminUsers' ? (
        <AdminUsersPage />
      ) : route.name === 'adminGyms' ? (
        <AdminGymsPage />
      ) : route.name === 'adminBookings' ? (
        <AdminBookingsPage />
      ) : route.name === 'checkout' ? (
        <CheckoutPage />
      ) : route.name === 'nearby' ? (
        <NearbyGymsPage />
      ) : route.name === 'gym' ? (
        <GymDetailsPage gymId={route.gymId} />
      ) : route.name === 'gymAccess' ? (
        <GymAccessPage gymId={route.gymId} />
      ) : route.name === 'membership' ? (
        <MembershipSubscriptionPage />
      ) : route.name === 'myAccess' ? (
        <StaticPage
          title="My Gym Access"
          description="Your active passes and recent check-ins will appear here."
        />
      ) : route.name === 'saved' ? (
        <StaticPage
          title="Saved Gyms"
          description="Your saved gyms will appear here so you can quickly return to them later."
        />
      ) : route.name === 'bookings' ? (
        <StaticPage
          title="Bookings"
          description="Your bookings and upcoming sessions will appear here."
        />
      ) : route.name === 'profile' ? (
        <UserProfilePage />
      ) : route.name === 'settings' ? (
        <StaticPage
          title="Settings"
          description="Update app preferences, privacy settings, and notifications here."
        />
      ) : route.name === 'classes' ? (
        <StaticPage
          title="Classes"
          description="Group classes will appear here. For now, explore gyms and check available class slots from a gym page."
          backTo="/profile"
        />
      ) : (
        <HomePage
          user={user}
          headerCtaText={headerCtaText}
          initials={initials}
          onOpenAuth={(intent) => {
            setLoginIntent(intent)
            setAuthOpen(true)
          }}
          onLogout={() => {
            clearTokens()
            setUser(null)
          }}
        />
      )}

      <AuthModal
        open={authOpen}
        onClose={() => setAuthOpen(false)}
        onAuthed={(payload) => {
          setTokens(payload.access_token, payload.refresh_token)
          setUser({ firstName: payload.user.first_name ?? 'Member', email: payload.user.email })
          setAuthOpen(false)
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
