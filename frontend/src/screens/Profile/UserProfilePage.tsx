import { useEffect, useMemo, useRef, useState } from 'react'
import styles from './profile.module.css'
import { navigate } from '../../router'
import { authFetch, clearTokens } from '../../auth'

type Profile = {
  user_id: number
  full_name: string
  profile_image: string | null
  member_since: string
  membership_status: string | null
}

type MembershipSummary = {
  membership_id: number | null
  plan_name: string | null
  status: string | null
  start_date: string | null
  end_date: string | null

  membership_scope: string | null
  active_gyms: { gym_id: number; gym_name: string; locality?: string | null; city?: string | null }[]

  remaining_visits: number | null
  total_visits: number | null
  gym_access_count: number
  visits_booked?: number | null
  visits_completed?: number | null
  pause_days_used?: number | null
  pause_days_remaining?: number | null
  membership_features: string[]
}

type ActivityBreakdownItem = {
  key: string
  label: string
  count: number
}

type Activity = {
  total_gym_visits: number
  total_classes_attended: number
  current_streak_days: number
  partner_gyms_visited: number
  activity_breakdown: ActivityBreakdownItem[]
}

type BookingItem = {
  booking_id: number
  booking_status: string
  attendance_status: string | null
  gym_id: number
  gym_name: string
  gym_location: string
  access_type: string
  class_name: string | null
  visit_date: string
  start_time: string
  end_time: string
  membership_covered: boolean
  amount_paid: string | null
  currency: string
  booking_created_at: string
  cancelled_at: string | null
}

type MembershipPass = {
  member_id: string
  full_name: string
  plan_name: string | null
  status: string | null
  valid_until: string | null
  qr_payload: string
  gym_access_count: number

  membership_scope?: string | null
  active_gyms?: { gym_id: number; gym_name: string; locality?: string | null; city?: string | null }[]
  visits_booked?: number | null
  visits_completed?: number | null
  pause_days_used?: number | null
  pause_days_remaining?: number | null
}

type Favorites = {
  gyms: { gym_id: number; gym_name: string; gym_location: string; visit_count: number }[]
}

type LoadState<T> =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: T }

function formatMonthYear(d: Date) {
  return d.toLocaleString(undefined, { month: 'short', year: 'numeric' })
}

function formatDayLabel(d: Date) {
  return d.toLocaleString(undefined, { weekday: 'short' })
}

function formatTime(t: string) {
  // t is "HH:MM:SS".
  const [hh, mm] = t.split(':')
  const h = Number(hh)
  const ampm = h >= 12 ? 'PM' : 'AM'
  const h12 = h % 12 === 0 ? 12 : h % 12
  return `${h12}:${mm} ${ampm}`
}

function groupByMonth(items: BookingItem[]) {
  const groups = new Map<string, BookingItem[]>()
  for (const it of items) {
    const dt = new Date(`${it.visit_date}T00:00:00`)
    const key = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}`
    const cur = groups.get(key) ?? []
    cur.push(it)
    groups.set(key, cur)
  }

  // Sort groups desc
  const entries = Array.from(groups.entries()).sort((a, b) => (a[0] < b[0] ? 1 : -1))
  return entries.map(([key, arr]) => {
    const [y, m] = key.split('-')
    const monthDate = new Date(Number(y), Number(m) - 1, 1)
    // Sort cards by date asc inside month (like reference)
    arr.sort((x, y2) => (x.visit_date > y2.visit_date ? 1 : x.visit_date < y2.visit_date ? -1 : x.start_time.localeCompare(y2.start_time)))
    return { key, label: formatMonthYear(monthDate), items: arr }
  })
}

function Badge({ tone, children }: { tone: 'neutral' | 'success' | 'warn' | 'danger' | 'brand'; children: string }) {
  return <span className={`${styles.badge} ${styles[`badge_${tone}`]}`}>{children}</span>
}

function SkeletonLine({ w, h = 14, r = 10 }: { w: number | string; h?: number; r?: number }) {
  return <div className={styles.skeleton} style={{ width: w, height: h, borderRadius: r }} aria-hidden="true" />
}

function ProfileMenu() {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node
      if (!wrapRef.current?.contains(target)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  const items = [
    { label: 'My Profile', to: '/profile' },
    { label: 'Membership', to: '/membership' },
    { label: 'My Bookings', to: '/bookings' },
    { label: 'Settings', to: '/settings' },
    { label: 'Logout', to: '/' }
  ]

  return (
    <div className={styles.profileWrap} ref={wrapRef}>
      <button type="button" className={styles.profileBtn} onClick={() => setOpen((v) => !v)} aria-label="Open profile menu">
        <span className={styles.profileAvatar} aria-hidden="true" />
      </button>
      {open ? (
        <div className={styles.profileDropdown} role="menu" aria-label="Profile">
          {items.map((it) => (
            <button
              key={it.label}
              type="button"
              className={styles.profileItem}
              onClick={() => {
                setOpen(false)
                if (it.label === 'Logout') {
                  clearTokens()
                  navigate(it.to)
                  return
                }
                navigate(it.to)
              }}
            >
              {it.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export default function UserProfilePage() {
  const [tab, setTab] = useState<'visits' | 'pass' | 'wallet'>('visits')
  const [filter, setFilter] = useState<'upcoming' | 'past' | 'cancelled'>('upcoming')
  const [activityFilter, setActivityFilter] = useState<string>('All Activities')

  const [profile, setProfile] = useState<LoadState<Profile>>({ status: 'loading' })
  const [membership, setMembership] = useState<LoadState<MembershipSummary>>({ status: 'loading' })
  const [activity, setActivity] = useState<LoadState<Activity>>({ status: 'loading' })
  const [favorites, setFavorites] = useState<LoadState<Favorites>>({ status: 'loading' })
  const [bookings, setBookings] = useState<LoadState<BookingItem[]>>({ status: 'loading' })
  const [pass, setPass] = useState<LoadState<MembershipPass>>({ status: 'loading' })

  const [wallet, setWallet] = useState<LoadState<{ balance: string; currency: string; transactions: any[] }>>({ status: 'loading' })
  const [walletTopupAmt, setWalletTopupAmt] = useState<number>(500)
  const [walletTopupBusy, setWalletTopupBusy] = useState(false)

  const [ratingOpen, setRatingOpen] = useState(false)
  const [ratingTarget, setRatingTarget] = useState<{ booking: BookingItem; rating: number; comment: string } | null>(null)
  const [ratingSubmitting, setRatingSubmitting] = useState(false)
  const [ratingError, setRatingError] = useState<string | null>(null)

  const now = useMemo(() => new Date(), [])

  useEffect(() => {
    let cancelled = false
    Promise.all([
      authFetch('/api/v1/profile').then(async (r) => {
        if (!r.ok) throw new Error('Failed to load profile')
        return (await r.json()) as Profile
      }),
      authFetch('/api/v1/profile/membership').then(async (r) => {
        if (!r.ok) throw new Error('Failed to load membership')
        return (await r.json()) as MembershipSummary
      }),
      authFetch('/api/v1/profile/activity').then(async (r) => {
        if (!r.ok) throw new Error('Failed to load activity')
        return (await r.json()) as Activity
      }),
      authFetch('/api/v1/profile/favorites').then(async (r) => {
        if (!r.ok) throw new Error('Failed to load favorites')
        return (await r.json()) as Favorites
      }),
      authFetch('/api/v1/profile/membership/pass').then(async (r) => {
        if (!r.ok) throw new Error('Failed to load pass')
        return (await r.json()) as MembershipPass
      }),
      authFetch('/api/v1/wallet/transactions?limit=50').then(async (r) => {
        if (!r.ok) throw new Error('Failed to load wallet')
        return (await r.json()) as { balance: string; currency: string; transactions: any[] }
      })
    ])
      .then(([p, m, a, f, mp, w]) => {
        if (cancelled) return
        setProfile({ status: 'ready', data: p })
        setMembership({ status: 'ready', data: m })
        setActivity({ status: 'ready', data: a })
        setFavorites({ status: 'ready', data: f })
        setPass({ status: 'ready', data: mp })
        setWallet({ status: 'ready', data: w })
      })
      .catch((e) => {
        if (cancelled) return
        const msg = e instanceof Error ? e.message : 'Failed to load'
        setProfile({ status: 'error', message: msg })
        setMembership({ status: 'error', message: msg })
        setActivity({ status: 'error', message: msg })
        setFavorites({ status: 'error', message: msg })
        setPass({ status: 'error', message: msg })
        setWallet({ status: 'error', message: msg })
      })
    return () => {
      cancelled = true
    }
  }, [])

  const reloadWallet = async () => {
    setWallet({ status: 'loading' })
    const r = await authFetch('/api/v1/wallet/transactions?limit=50')
    if (!r.ok) {
      setWallet({ status: 'error', message: 'Failed to load wallet' })
      return
    }
    const data = (await r.json()) as { balance: string; currency: string; transactions: any[] }
    setWallet({ status: 'ready', data })
  }

  const topupWallet = async () => {
    if (walletTopupBusy) return
    setWalletTopupBusy(true)
    try {
      const r = await authFetch('/api/v1/wallet/topup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount: Number(walletTopupAmt) })
      })
      if (!r.ok) {
        const data = await r.json().catch(() => ({}))
        throw new Error(data?.detail ?? 'Top up failed')
      }
      await reloadWallet()
    } finally {
      setWalletTopupBusy(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    setBookings({ status: 'loading' })
    authFetch(`/api/v1/profile/bookings?status=${encodeURIComponent(filter)}`)
      .then(async (r) => {
        if (!r.ok) {
          const data = await r.json().catch(() => ({}))
          throw new Error(data?.detail ?? 'Failed to load visits')
        }
        return (await r.json()) as BookingItem[]
      })
      .then((items) => {
        if (cancelled) return
        setBookings({ status: 'ready', data: items })
      })
      .catch((e) => {
        if (cancelled) return
        setBookings({ status: 'error', message: e instanceof Error ? e.message : 'Failed to load visits' })
      })
    return () => {
      cancelled = true
    }
  }, [filter])

  const grouped = useMemo(() => (bookings.status === 'ready' ? groupByMonth(bookings.data) : []), [bookings])

  const memberSinceText = useMemo(() => {
    if (profile.status !== 'ready') return ''
    const d = new Date(profile.data.member_since)
    return d.toLocaleString(undefined, { month: 'short', year: 'numeric' })
  }, [profile])

  const membershipTone = useMemo(() => {
    if (membership.status !== 'ready') return 'neutral' as const
    const st = membership.data.status
    if (st === 'ACTIVE') return 'success' as const
    if (st === 'EXPIRED') return 'danger' as const
    if (st === 'CANCELLED') return 'warn' as const
    return 'neutral' as const
  }, [membership])

  const membershipBadge = useMemo(() => {
    if (membership.status !== 'ready') return null
    const m = membership.data
    if (!m.status) return null
    if (m.status === 'ACTIVE') return { tone: 'success' as const, label: '● Active' }
    if (m.status === 'EXPIRED') return { tone: 'danger' as const, label: '● Membership Expired' }
    if (m.status === 'CANCELLED') return { tone: 'warn' as const, label: '● Cancelled' }
    return { tone: 'neutral' as const, label: m.status }
  }, [membership])

  const membershipLabel = useMemo(() => {
    if (membership.status !== 'ready') return null
    const m = membership.data
    if (!m.status) return null
    if (m.status === 'ACTIVE' && m.end_date) {
      const end = new Date(m.end_date)
      const diffDays = Math.ceil((end.getTime() - Date.now()) / (1000 * 60 * 60 * 24))
      if (diffDays <= 7 && diffDays > 0) return { tone: 'warn' as const, label: `● Expires in ${diffDays} days` }
    }
    return membershipBadge
  }, [membership, membershipBadge])

  const membershipGymSummary = useMemo(() => {
    if (membership.status !== 'ready') return null
    const gyms = membership.data.active_gyms ?? []
    if (!gyms.length) return null
    const names = gyms.map((g) => g.gym_name).filter(Boolean)
    if (names.length <= 2) return names.join(', ')
    return `${names.slice(0, 2).join(', ')} +${names.length - 2}`
  }, [membership])

  const visitEmpty = useMemo(() => {
    if (bookings.status !== 'ready') return false
    return bookings.data.length === 0
  }, [bookings])

  const canRate = (b: BookingItem) => {
    // Only if attendance is ATTENDED and not cancelled.
    return b.attendance_status === 'ATTENDED' && b.booking_status !== 'CANCELLED'
  }

  const openRating = (b: BookingItem) => {
    setRatingError(null)
    setRatingTarget({ booking: b, rating: 0, comment: '' })
    setRatingOpen(true)
  }

  const submitRating = async () => {
    if (!ratingTarget) return
    setRatingError(null)
    if (ratingTarget.rating <= 0) {
      setRatingError('Please select a rating')
      return
    }
    setRatingSubmitting(true)
    try {
      const r = await authFetch(`/api/v1/gyms/${ratingTarget.booking.gym_id}/reviews`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rating: ratingTarget.rating, comment: ratingTarget.comment || null })
      })
      if (!r.ok) {
        const data = await r.json().catch(() => ({}))
        throw new Error(data?.detail ?? 'Failed to submit review')
      }
      setRatingOpen(false)
      setRatingTarget(null)
    } catch (e) {
      setRatingError(e instanceof Error ? e.message : 'Failed to submit review')
    } finally {
      setRatingSubmitting(false)
    }
  }

  return (
    <div className={styles.pageRoot}>
      <header className={styles.navbar}>
        <div className={styles.navLeft}>
          <a
            className={styles.logo}
            href="/"
            onClick={(e) => {
              e.preventDefault()
              navigate('/')
            }}
            aria-label="FitiGo home"
          >
            FitiGo
          </a>
        </div>

        <nav className={styles.navCenter} aria-label="Primary">
          <a className={styles.navItem} href="/nearby" onClick={(e) => { e.preventDefault(); navigate('/nearby') }}>
            Explore
          </a>
          <a className={styles.navItem} href="/nearby" onClick={(e) => { e.preventDefault(); navigate('/nearby') }}>
            Gyms
          </a>
          <a className={styles.navItem} href="/membership" onClick={(e) => { e.preventDefault(); navigate('/membership') }}>
            Membership
          </a>
          <a className={styles.navItem} href="/classes" onClick={(e) => { e.preventDefault(); navigate('/classes') }}>
            Classes
          </a>
        </nav>

        <div className={styles.navRight}>
          <ProfileMenu />
        </div>
      </header>

      <main className={styles.content}>
        <div className={styles.layout}>
          <aside className={styles.sidebar}>
            <section className={styles.card}>
              {profile.status === 'loading' ? (
                <div>
                  <div className={styles.profileHeader}>
                    <div className={`${styles.avatar} ${styles.skeleton}`} />
                    <div style={{ flex: 1 }}>
                      <SkeletonLine w={160} h={18} />
                      <div style={{ height: 10 }} />
                      <SkeletonLine w={130} h={12} />
                    </div>
                  </div>
                  <div className={styles.statGrid}>
                    {Array.from({ length: 3 }).map((_, i) => (
                      <div key={i} className={styles.statRow}>
                        <SkeletonLine w={110} h={12} />
                        <SkeletonLine w={30} h={12} />
                      </div>
                    ))}
                  </div>
                  <div className={styles.cardActionRow}>
                    <div className={`${styles.actionBtn} ${styles.actionBtnSkeleton}`}>
                      <SkeletonLine w={140} h={14} />
                    </div>
                  </div>
                </div>
              ) : profile.status === 'error' ? (
                <div className={styles.errorBlock}>
                  <div className={styles.errorTitle}>Unable to load profile</div>
                  <div className={styles.errorMsg}>{profile.message}</div>
                  <button type="button" className={styles.primaryBtn} onClick={() => window.location.reload()}>
                    Retry
                  </button>
                </div>
              ) : (
                <div>
                  <div className={styles.profileHeader}>
                    <div className={styles.avatar}>
                      {profile.data.profile_image ? (
                        <img src={profile.data.profile_image} alt="Profile" className={styles.avatarImg} />
                      ) : (
                        <div className={styles.avatarFallback} aria-hidden="true">
                          {profile.data.full_name.slice(0, 1).toUpperCase()}
                        </div>
                      )}
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div className={styles.profileName} title={profile.data.full_name}>
                        {profile.data.full_name}
                      </div>
                      <div className={styles.profileSub}>
                        {membership.status === 'ready' && membership.data.plan_name ? (
                          <>
                            <span style={{ fontWeight: 700 }}>{membership.data.plan_name}</span>
                            <span className={styles.dot} aria-hidden="true">
                              ·
                            </span>
                          </>
                        ) : null}
                        <span>Member since {memberSinceText}</span>
                      </div>
                    </div>
                  </div>

                  <div className={styles.statGrid}>
                    <div className={styles.statRow}>
                      <div className={styles.statLabel}>Gym Visits</div>
                      <div className={styles.statValue}>
                        {activity.status === 'ready' ? activity.data.total_gym_visits : '—'}
                      </div>
                    </div>
                    <div className={styles.statRow}>
                      <div className={styles.statLabel}>Classes Attended</div>
                      <div className={styles.statValue}>
                        {activity.status === 'ready' ? activity.data.total_classes_attended : '—'}
                      </div>
                    </div>
                    <div className={styles.statRow}>
                      <div className={styles.statLabel}>Current Streak</div>
                      <div className={styles.statValue}>
                        {activity.status === 'ready' ? `${activity.data.current_streak_days} Days` : '—'}
                      </div>
                    </div>
                  </div>

                  <div className={styles.subCard}>
                    <div className={styles.subCardHeader}>
                      <div>
                        <div className={styles.subCardKicker}>ACTIVE MEMBERSHIP</div>
                        <div className={styles.subCardTitle}>{membership.status === 'ready' ? membership.data.plan_name ?? '—' : '—'}</div>
                      </div>
                      {membershipLabel ? <Badge tone={membershipLabel.tone}>{membershipLabel.label}</Badge> : <Badge tone="neutral">—</Badge>}
                    </div>
                    <div className={styles.subCardBody}>
                      <div className={styles.subCardMeta}>
                        {membership.status === 'ready' && membership.data.end_date ? (
                          <>Valid until {new Date(membership.data.end_date).toLocaleDateString()}</>
                        ) : (
                          <>No active membership</>
                        )}
                      </div>

                      {membership.status === 'ready' && membershipGymSummary ? (
                        <div className={styles.subCardMeta}>
                          Applies to: <span style={{ fontWeight: 850 }}>{membershipGymSummary}</span>
                        </div>
                      ) : null}

                      {membership.status === 'ready' && (membership.data.visits_booked != null || membership.data.visits_completed != null) ? (
                        <div className={styles.subCardMeta}>
                          Visits: {membership.data.visits_completed ?? 0} completed / {membership.data.visits_booked ?? 0} booked
                        </div>
                      ) : null}

                      {membership.status === 'ready' && membership.data.pause_days_remaining != null ? (
                        <div className={styles.subCardMeta}>
                          Pause days remaining: {membership.data.pause_days_remaining} / 60
                        </div>
                      ) : null}

                      <button
                        type="button"
                        className={styles.linkBtn}
                        onClick={() => navigate('/membership')}
                        disabled={membership.status !== 'ready' || !membership.data.membership_id}
                        aria-disabled={membership.status !== 'ready' || !membership.data.membership_id ? 'true' : 'false'}
                      >
                        {membership.status === 'ready' && membership.data.membership_id ? 'VIEW MEMBERSHIP' : 'EXPLORE MEMBERSHIP PLANS'}
                      </button>
                    </div>
                  </div>

                  <div className={styles.cardActionRow}>
                    <button type="button" className={styles.manageBtn} onClick={() => navigate('/settings')}>
                      <span className={styles.manageIcon} aria-hidden="true">
                        ✎
                      </span>
                      MANAGE PROFILE
                    </button>
                  </div>
                </div>
              )}
            </section>

            <section className={styles.card}>
              <div className={styles.cardHeaderRow}>
                <div>
                  <div className={styles.cardTitle}>My Fitness Activity</div>
                </div>
                <select
                  className={styles.dropdown}
                  value={activityFilter}
                  onChange={(e) => setActivityFilter(e.target.value)}
                  aria-label="Activity filter"
                >
                  <option>All Activities</option>
                  <option>Gym Workout</option>
                  <option>Yoga</option>
                  <option>HIIT</option>
                  <option>Strength Training</option>
                  <option>Cardio</option>
                  <option>Group Classes</option>
                </select>
              </div>

              {activity.status === 'loading' ? (
                <div className={styles.activityRows}>
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className={styles.statRow}>
                      <SkeletonLine w={160} h={12} />
                      <SkeletonLine w={60} h={12} />
                    </div>
                  ))}
                </div>
              ) : activity.status === 'error' ? (
                <div className={styles.mutedSmall}>Unable to load activity.</div>
              ) : (
                  <div className={styles.activityRows}>
                    <div className={styles.statRow}>
                      <div className={styles.statLabel}>Overall Activity Level</div>
                      <div className={styles.statValue}>{activity.data.total_gym_visits > 0 ? 'Active' : '—'}</div>
                    </div>
                    <div className={styles.statRow}>
                      <div className={styles.statLabel}>Partner Gyms Visited</div>
                      <div className={styles.statValue}>{activity.data.partner_gyms_visited}</div>
                    </div>
                    <div className={styles.statRow}>
                      <div className={styles.statLabel}>Current Streak</div>
                      <div className={styles.statValue}>{activity.data.current_streak_days} Days</div>
                    </div>
                  </div>
              )}

              <div className={styles.cardFooterAction}>
                <button type="button" className={styles.manageBtn} onClick={() => navigate('/settings')}>
                  EDIT FITNESS PREFERENCES
                </button>
              </div>
            </section>

            <section className={styles.card}>
              <div className={styles.cardHeaderRow}>
                <div className={styles.cardTitle}>Favorite Gyms</div>
              </div>
              {favorites.status === 'loading' ? (
                <div className={styles.favList}>
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className={styles.favRow}>
                      <SkeletonLine w={'70%'} h={12} />
                      <SkeletonLine w={36} h={12} />
                    </div>
                  ))}
                </div>
              ) : favorites.status === 'error' ? (
                <div className={styles.mutedSmall}>Unable to load favorites.</div>
              ) : favorites.data.gyms.length === 0 ? (
                <div className={styles.mutedSmall}>No favorites yet.</div>
              ) : (
                <div className={styles.favList}>
                  {favorites.data.gyms.map((g) => (
                    <button
                      key={g.gym_id}
                      type="button"
                      className={styles.favItem}
                      onClick={() => navigate(`/gyms/${g.gym_id}`)}
                    >
                      <div className={styles.favName} title={g.gym_name}>
                        {g.gym_name}
                      </div>
                      <div className={styles.favMeta}>{g.visit_count} visits</div>
                    </button>
                  ))}
                </div>
              )}
            </section>
          </aside>

          <section className={styles.mainPanel}>
            <div className={styles.panelCard}>
              <div className={styles.panelTabs}>
                <button
                  type="button"
                  className={`${styles.panelTab} ${tab === 'visits' ? styles.panelTabActive : ''}`}
                  onClick={() => setTab('visits')}
                >
                  My Visits
                </button>
                <button
                  type="button"
                  className={`${styles.panelTab} ${tab === 'pass' ? styles.panelTabActive : ''}`}
                  onClick={() => setTab('pass')}
                >
                  Membership Pass
                </button>
                <button
                  type="button"
                  className={`${styles.panelTab} ${tab === 'wallet' ? styles.panelTabActive : ''}`}
                  onClick={() => setTab('wallet')}
                >
                  FitiGo Wallet
                </button>
              </div>
              <div className={styles.panelDivider} />

              {tab === 'visits' ? (
                <>
                  <div className={styles.filterRow}>
                    <button
                      type="button"
                      className={`${styles.filterBtn} ${filter === 'upcoming' ? styles.filterBtnActive : ''}`}
                      onClick={() => setFilter('upcoming')}
                    >
                      UPCOMING
                    </button>
                    <button
                      type="button"
                      className={`${styles.filterBtn} ${filter === 'past' ? styles.filterBtnActive : ''}`}
                      onClick={() => setFilter('past')}
                    >
                      PAST
                    </button>
                    <button
                      type="button"
                      className={`${styles.filterBtn} ${filter === 'cancelled' ? styles.filterBtnActive : ''}`}
                      onClick={() => setFilter('cancelled')}
                    >
                      CANCELLED
                    </button>
                  </div>

                  <div className={styles.visitsWrap}>
                    {bookings.status === 'loading' ? (
                      <div>
                        {Array.from({ length: 3 }).map((_, mi) => (
                          <div key={mi} className={styles.monthBlock}>
                            <SkeletonLine w={120} h={16} />
                            <div style={{ height: 12 }} />
                            {Array.from({ length: 2 }).map((__, ci) => (
                              <div key={ci} className={styles.visitCard} aria-hidden="true">
                                <div className={`${styles.dateBadge} ${styles.dateBadgeSkeleton}`}>
                                  <SkeletonLine w={30} h={10} r={6} />
                                  <div style={{ height: 6 }} />
                                  <SkeletonLine w={20} h={14} r={6} />
                                </div>
                                <div className={styles.visitBody}>
                                  <div className={styles.visitTopRow}>
                                    <div style={{ minWidth: 0 }}>
                                      <SkeletonLine w={'78%'} h={12} />
                                      <div style={{ height: 8 }} />
                                      <SkeletonLine w={'55%'} h={12} />
                                    </div>
                                    <div className={styles.visitTopRight}>
                                      <SkeletonLine w={110} h={22} r={999} />
                                      <SkeletonLine w={90} h={22} r={999} />
                                    </div>
                                  </div>
                                  <div className={styles.visitChipsRow}>
                                    <SkeletonLine w={90} h={20} r={999} />
                                    <SkeletonLine w={80} h={12} />
                                  </div>
                                  <div className={styles.cardActionsRow}>
                                    <SkeletonLine w={90} h={32} r={10} />
                                    <SkeletonLine w={90} h={32} r={10} />
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        ))}
                      </div>
                    ) : bookings.status === 'error' ? (
                      <div className={styles.errorBlock}>
                        <div className={styles.errorTitle}>Unable to load visits</div>
                        <div className={styles.errorMsg}>{bookings.message}</div>
                        <button type="button" className={styles.primaryBtn} onClick={() => setFilter((f) => f)}>
                          Retry
                        </button>
                      </div>
                    ) : visitEmpty ? (
                      <div className={styles.emptyState}>
                        <div className={styles.emptyTitle}>
                          {filter === 'upcoming'
                            ? 'No upcoming visits'
                            : filter === 'past'
                              ? 'Your fitness journey starts here'
                              : 'No cancelled bookings'}
                        </div>
                        <div className={styles.emptyDesc}>
                          {filter === 'upcoming'
                            ? 'Explore gyms near you and plan your next workout.'
                            : filter === 'past'
                              ? 'Your completed gym visits and classes will appear here.'
                              : 'Cancelled bookings will appear here.'}
                        </div>
                        <button type="button" className={styles.primaryBtn} onClick={() => navigate('/nearby')}>
                          Explore Gyms
                        </button>
                      </div>
                    ) : (
                      <div>
                        {grouped.map((g) => (
                          <div key={g.key} className={styles.monthBlock}>
                            <div className={styles.monthTitle}>{g.label}</div>
                            <div className={styles.cardsCol}>
                              {g.items.map((b) => {
                                const dt = new Date(`${b.visit_date}T00:00:00`)
                                const statusTone =
                                  b.booking_status === 'COMPLETED'
                                    ? ('success' as const)
                                    : b.booking_status === 'MISSED'
                                      ? ('warn' as const)
                                      : b.booking_status === 'CANCELLED'
                                        ? ('danger' as const)
                                        : b.booking_status === 'CONFIRMED'
                                          ? ('brand' as const)
                                          : ('neutral' as const)

                                const payLabel = b.membership_covered
                                  ? 'MEMBERSHIP INCLUDED'
                                  : b.amount_paid
                                    ? `${b.currency} ${b.amount_paid}`
                                    : 'PAID DAY PASS'

                                const startDt = new Date(`${b.visit_date}T${b.start_time}`)
                                const minutesToStart = Math.round((startDt.getTime() - Date.now()) / (1000 * 60))
                                const cancelDisabled = minutesToStart < 120

                                 return (
                                   <div key={b.booking_id} className={styles.visitCard}>
                                     <div className={styles.dateBadge} aria-label="Date">
                                       <div className={styles.dateDow}>{formatDayLabel(dt)}</div>
                                       <div className={styles.dateNum}>{dt.getDate()}</div>
                                     </div>

                                     <div className={styles.visitBody}>
                                       <div className={styles.visitTopRow}>
                                         <div style={{ minWidth: 0 }}>
                                           <div className={styles.visitTitle} title={b.class_name ? `${b.class_name} - ${b.gym_name}` : b.gym_name}>
                                             {b.class_name ? (
                                               <>
                                                 <span className={styles.visitTitleMain}>{b.class_name}</span>
                                                 <span className={styles.visitTitleSub}> — {b.gym_name}</span>
                                               </>
                                             ) : (
                                               <span className={styles.visitTitleMain}>{b.gym_name}</span>
                                             )}
                                           </div>

                                           <div className={styles.visitMetaLine}>
                                             <span className={styles.visitTime}>
                                               {formatTime(b.start_time)} – {formatTime(b.end_time)}
                                             </span>
                                             <span className={styles.metaDot} aria-hidden="true">
                                               •
                                             </span>
                                             <span className={styles.visitSubtitle} title={b.gym_location}>
                                               {b.gym_location || '—'}
                                             </span>
                                           </div>
                                         </div>

                                         <div className={styles.visitTopRight}>
                                           <Badge tone={statusTone}>{b.booking_status}</Badge>
                                           <div className={styles.payChip}>{payLabel}</div>
                                         </div>
                                       </div>

                                       <div className={styles.visitChipsRow}>
                                         <span className={styles.chip}>{b.access_type}</span>
                                         <span className={styles.bookingIdInline}>ID: {String(b.booking_id)}</span>
                                         {filter === 'cancelled' && b.cancelled_at ? (
                                           <span className={styles.cancelMetaInline}>
                                             Cancelled on {new Date(b.cancelled_at).toLocaleDateString()}
                                           </span>
                                         ) : null}
                                       </div>

                                       <div className={styles.cardActionsRow}>
                                         <button type="button" className={styles.tertiaryBtn} onClick={() => navigate(`/gyms/${b.gym_id}`)}>
                                           View Details
                                         </button>
                                         <button
                                           type="button"
                                           className={styles.tertiaryBtn}
                                           onClick={() =>
                                             window.open(
                                               `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${b.gym_name} ${b.gym_location}`)}`,
                                               '_blank'
                                             )
                                           }
                                         >
                                           Directions
                                         </button>

                                         {filter === 'upcoming' && b.booking_status !== 'CANCELLED' ? (
                                           <button
                                             type="button"
                                             className={styles.dangerBtnSmall}
                                             onClick={() => navigate('/bookings')}
                                             disabled={cancelDisabled}
                                             title={cancelDisabled ? 'Cancellations are disabled close to start time' : 'Cancel booking'}
                                           >
                                             Cancel
                                           </button>
                                         ) : null}

                                         {filter === 'past' && canRate(b) ? (
                                           <button type="button" className={styles.primaryBtnSmall} onClick={() => openRating(b)}>
                                             Rate
                                           </button>
                                         ) : null}
                                       </div>
                                     </div>
                                   </div>
                                 )
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              ) : tab === 'pass' ? (
                <div className={styles.passWrap}>
                  {pass.status === 'loading' ? (
                    <div className={styles.passCard}>
                      <SkeletonLine w={220} h={14} />
                      <div style={{ height: 12 }} />
                      <SkeletonLine w={160} h={20} />
                      <div style={{ height: 20 }} />
                      <SkeletonLine w={'60%'} h={14} />
                      <div style={{ height: 8 }} />
                      <SkeletonLine w={140} h={14} />
                      <div style={{ height: 22 }} />
                      <div className={styles.qrPlaceholder} aria-hidden="true">
                        <div className={styles.qrInner}>QR</div>
                      </div>
                    </div>
                  ) : pass.status === 'error' ? (
                    <div className={styles.errorBlock}>
                      <div className={styles.errorTitle}>Unable to load membership pass</div>
                      <div className={styles.errorMsg}>{pass.message}</div>
                    </div>
                  ) : (
                    <>
                      <div className={styles.passCard}>
                        <div className={styles.passKicker}>MULTI-GYM MEMBERSHIP</div>
                        <div className={styles.passPlan}>{pass.data.plan_name ?? 'Membership'}</div>
                        <div className={styles.passName}>{pass.data.full_name}</div>
                        <div className={styles.passMeta}>Member ID: {pass.data.member_id}</div>
                        <div className={styles.passMeta}>
                          Valid Until: {pass.data.valid_until ? new Date(pass.data.valid_until).toLocaleDateString() : '—'}
                        </div>
                        <div className={styles.qrBlock}>
                          <div className={styles.qrPlaceholder} aria-label="Membership QR">
                            <div className={styles.qrInner}>QR</div>
                          </div>
                          <div className={styles.qrText} title={pass.data.qr_payload}>
                            {pass.data.qr_payload}
                          </div>
                        </div>
                      </div>

                      <div className={styles.passInfoGrid}>
                        <div className={styles.infoRow}>
                          <div className={styles.infoLabel}>Status</div>
                          <div className={styles.infoValue}>
                            <Badge tone={membershipTone}>{pass.data.status ?? '—'}</Badge>

                        {pass.data.visits_booked != null || pass.data.visits_completed != null ? (
                          <div className={styles.infoRow}>
                            <div className={styles.infoLabel}>Visits</div>
                            <div className={styles.infoValue}>
                              {pass.data.visits_completed ?? 0} completed / {pass.data.visits_booked ?? 0} booked
                            </div>
                          </div>
                        ) : null}

                        {pass.data.pause_days_remaining != null ? (
                          <div className={styles.infoRow}>
                            <div className={styles.infoLabel}>Pause Days</div>
                            <div className={styles.infoValue}>{pass.data.pause_days_remaining} remaining (max 60)</div>
                          </div>
                        ) : null}
                          </div>
                        </div>
                        <div className={styles.infoRow}>
                          <div className={styles.infoLabel}>Gym Access</div>
                          <div className={styles.infoValue}>{pass.data.gym_access_count} partner gyms</div>
                        </div>

                        {pass.data.visits_booked != null || pass.data.visits_completed != null ? (
                          <div className={styles.infoRow}>
                            <div className={styles.infoLabel}>Visits</div>
                            <div className={styles.infoValue}>
                              {pass.data.visits_completed ?? 0} completed / {pass.data.visits_booked ?? 0} booked
                            </div>
                          </div>
                        ) : null}

                        {pass.data.pause_days_remaining != null ? (
                          <div className={styles.infoRow}>
                            <div className={styles.infoLabel}>Pause Days</div>
                            <div className={styles.infoValue}>{pass.data.pause_days_remaining} remaining (max 60)</div>
                          </div>
                        ) : null}
                      </div>

                      <div className={styles.passActions}>
                        <button type="button" className={styles.secondaryBtn} onClick={() => navigate('/membership')}>
                          VIEW PLAN DETAILS
                        </button>
                        <button type="button" className={styles.secondaryBtn} onClick={() => navigate('/membership')}>
                          UPGRADE PLAN
                        </button>
                        <button type="button" className={styles.secondaryBtn} onClick={() => navigate('/membership')}>
                          RENEW MEMBERSHIP
                        </button>
                        <button type="button" className={styles.secondaryBtn} onClick={() => navigate('/membership')}>
                          PAYMENT HISTORY
                        </button>
                      </div>
                    </>
                  )}
                </div>
              ) : (
                <div style={{ padding: 16 }}>
                  <div style={{ fontWeight: 950 }}>Wallet Balance</div>
                  {wallet.status === 'loading' ? (
                    <div className={styles.muted} style={{ marginTop: 8 }}>
                      Loading wallet…
                    </div>
                  ) : wallet.status === 'error' ? (
                    <div className={styles.errorBlock}>
                      <div className={styles.errorTitle}>Unable to load wallet</div>
                      <div className={styles.errorMsg}>{wallet.message}</div>
                      <button type="button" className={styles.primaryBtn} onClick={reloadWallet}>
                        Retry
                      </button>
                    </div>
                  ) : (
                    <>
                      <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                        <div className={styles.muted}>Available Balance</div>
                        <div style={{ fontWeight: 950 }}>₹{Number(wallet.data.balance).toFixed(2)} {wallet.data.currency}</div>
                      </div>

                      <div style={{ marginTop: 14, borderTop: '1px solid var(--line)' }} />

                      <div style={{ marginTop: 14, fontWeight: 950 }}>Recharge Wallet</div>
                      <div style={{ display: 'flex', gap: 10, marginTop: 8, flexWrap: 'wrap' }}>
                        <input
                          className={styles.input}
                          type="number"
                          min={1}
                          value={String(walletTopupAmt)}
                          onChange={(e) => setWalletTopupAmt(Number(e.target.value || 0))}
                        />
                        <button type="button" className={styles.secondaryBtn} onClick={topupWallet} disabled={walletTopupBusy}>
                          {walletTopupBusy ? 'Recharging…' : 'Recharge'}
                        </button>
                      </div>
                      <div className={styles.muted} style={{ marginTop: 8 }}>
                        Money In will appear as TOPUP transactions. Money Out will appear as PAYMENT transactions.
                      </div>

                      <div style={{ marginTop: 14, borderTop: '1px solid var(--line)' }} />
                      <div style={{ marginTop: 14, fontWeight: 950 }}>Transaction History</div>
                      {wallet.data.transactions?.length ? (
                        <div style={{ marginTop: 10, display: 'grid', gap: 10 }}>
                          {wallet.data.transactions.map((t: any) => (
                            <div key={t.id} className={styles.infoRow} style={{ alignItems: 'start' }}>
                              <div className={styles.infoLabel}>
                                <div style={{ fontWeight: 900 }}>{t.txn_type}</div>
                                <div className={styles.muted}>{new Date(t.created_at).toLocaleString()}</div>
                                {t.description ? <div className={styles.muted}>{t.description}</div> : null}
                              </div>
                              <div className={styles.infoValue} style={{ fontWeight: 950 }}>
                                {t.direction === 'OUT' ? '-' : '+'}₹{Number(t.amount).toFixed(2)}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className={styles.muted} style={{ marginTop: 10 }}>
                          No wallet transactions yet.
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          </section>
        </div>
      </main>

      {ratingOpen && ratingTarget ? (
        <div className={styles.modalOverlay} role="dialog" aria-modal="true" aria-label="Rate your visit">
          <div className={styles.modalCard}>
            <div className={styles.modalHeader}>
              <div>
                <div className={styles.modalTitle}>How was your experience?</div>
                <div className={styles.modalSub}>
                  {ratingTarget.booking.gym_name}
                </div>
              </div>
              <button type="button" className={styles.modalClose} onClick={() => setRatingOpen(false)} aria-label="Close">
                ×
              </button>
            </div>

            <div className={styles.starsRow}>
              {Array.from({ length: 5 }).map((_, i) => {
                const v = i + 1
                const active = ratingTarget.rating >= v
                return (
                  <button
                    key={v}
                    type="button"
                    className={`${styles.starBtn} ${active ? styles.starBtnActive : ''}`}
                    onClick={() => setRatingTarget((cur) => (cur ? { ...cur, rating: v } : cur))}
                    aria-label={`${v} stars`}
                  >
                    ★
                  </button>
                )
              })}
            </div>

            <textarea
              className={styles.textarea}
              placeholder="Tell us more about your visit..."
              value={ratingTarget.comment}
              onChange={(e) => setRatingTarget((cur) => (cur ? { ...cur, comment: e.target.value } : cur))}
              rows={4}
            />

            {ratingError ? <div className={styles.formError}>{ratingError}</div> : null}

            <div className={styles.modalActions}>
              <button type="button" className={styles.secondaryBtn} onClick={() => setRatingOpen(false)} disabled={ratingSubmitting}>
                Cancel
              </button>
              <button type="button" className={styles.primaryBtn} onClick={submitRating} disabled={ratingSubmitting}>
                {ratingSubmitting ? 'Submitting…' : 'Submit Review'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
