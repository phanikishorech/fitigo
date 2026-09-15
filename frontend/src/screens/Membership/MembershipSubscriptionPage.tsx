import { useEffect, useMemo, useState } from 'react'
import styles from './membershipSubscription.module.css'
import { authFetch, getAccessToken } from '../../auth'
import { openAuthModal } from '../../authUi'
import { navigate } from '../../router'
import ProfileIconButton from '../../components/ProfileIconButton'
import AppDownloadModal from '../NearbyGyms/AppDownloadModal'

type GymListItem = {
  id: number
  name: string
  city: string | null
  distance_km?: number | null
  cover_image_url?: string | null
}

type MembershipPlan = {
  id: number
  gym_id: number
  name: string
  description: string | null
  duration_days: number
  price: string
  currency: string
  is_active: boolean
}

type PurchaseMembershipResponse = {
  id: number
  user_id: number
  gym_id: number
  plan_id: number
  status: string
  start_at: string
  end_at: string
  paid_amount: string
  currency: string
}

type AsyncState<T> =
  | { status: 'idle' | 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string }

const MULTI_GYM_BENEFITS: string[] = [
  'Access multiple partner gyms with one membership',
  'Workout anywhere — no long-term lock-in',
  'Seamless check-in from your Profile pass (QR)',
  'Member-only discounts on day passes and classes (where available)',
  'Priority support for booking and membership issues',
  'Pause/cancel anytime (MVP: cancellation is supported on purchased plans)'
]

const MULTI_GYM_PLANS = [
  {
    key: 'monthly',
    title: 'Multi Access — Monthly',
    durationLabel: '30 days',
    priceLabel: '₹1,499',
    subLabel: 'Best for trying multi-gym access'
  },
  {
    key: 'quarterly',
    title: 'Multi Access — Quarterly',
    durationLabel: '90 days',
    priceLabel: '₹3,999',
    subLabel: 'Save vs monthly'
  },
  {
    key: 'halfyearly',
    title: 'Multi Access — Half-Yearly',
    durationLabel: '180 days',
    priceLabel: '₹7,499',
    subLabel: 'For consistent training'
  },
  {
    key: 'yearly',
    title: 'Multi Access — Yearly',
    durationLabel: '365 days',
    priceLabel: '₹13,999',
    subLabel: 'Best value'
  }
] as const

export default function MembershipSubscriptionPage() {
  const [mode, setMode] = useState<'multi' | 'single'>('multi')

  const [multiNotice, setMultiNotice] = useState<string | null>(null)

  const [appOpen, setAppOpen] = useState(false)

  const [gyms, setGyms] = useState<AsyncState<GymListItem[]>>({ status: 'idle' })
  const [selectedGymId, setSelectedGymId] = useState<number | null>(null)
  const [plans, setPlans] = useState<AsyncState<MembershipPlan[]>>({ status: 'idle' })
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null)
  const [purchase, setPurchase] = useState<AsyncState<PurchaseMembershipResponse | null>>({ status: 'idle' })

  // Allow preselect by query string: /membership?gymId=123
  useEffect(() => {
    try {
      const qs = new URLSearchParams(window.location.search)
      const qGymId = qs.get('gymId')
      if (qGymId && !Number.isNaN(Number(qGymId))) {
        setMode('single')
        setSelectedGymId(Number(qGymId))
      }
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function loadGyms() {
      setGyms({ status: 'loading' })
      try {
        const r = await fetch('/api/v1/gyms?limit=80&offset=0')
        if (!r.ok) throw new Error('Failed to load gyms')
        const data = (await r.json()) as GymListItem[]
        if (cancelled) return
        setGyms({ status: 'ready', data })

        // If we didn't preselect, default to first gym for the single-gym flow.
        if (!selectedGymId && data.length > 0) {
          setSelectedGymId(data[0].id)
        }
      } catch (e) {
        if (cancelled) return
        setGyms({ status: 'error', message: e instanceof Error ? e.message : 'Unable to load gyms' })
      }
    }
    loadGyms()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selectedGymId) return
    let cancelled = false

    async function loadPlans() {
      setPlans({ status: 'loading' })
      setSelectedPlanId(null)
      try {
        const r = await fetch(`/api/v1/memberships/gyms/${selectedGymId}/plans`)
        if (!r.ok) throw new Error('Failed to load membership plans')
        const data = (await r.json()) as MembershipPlan[]
        if (cancelled) return
        const active = data.filter((p) => p.is_active)
        setPlans({ status: 'ready', data: active })
        if (active.length > 0) setSelectedPlanId(active[0].id)
      } catch (e) {
        if (cancelled) return
        setPlans({ status: 'error', message: e instanceof Error ? e.message : 'Unable to load membership plans' })
      }
    }

    loadPlans()
    return () => {
      cancelled = true
    }
  }, [selectedGymId])

  const selectedGym = useMemo(() => {
    if (gyms.status !== 'ready' || !selectedGymId) return null
    return gyms.data.find((g) => g.id === selectedGymId) ?? null
  }, [gyms, selectedGymId])

  const selectedPlan = useMemo(() => {
    if (plans.status !== 'ready' || !selectedPlanId) return null
    return plans.data.find((p) => p.id === selectedPlanId) ?? null
  }, [plans, selectedPlanId])

  async function handlePurchaseSingleGym() {
    if (!selectedGymId || !selectedPlanId) return

    const token = getAccessToken()
    if (!token) {
      openAuthModal('membership_purchase')
      return
    }

    setPurchase({ status: 'loading' })
    try {
      const r = await authFetch(`/api/v1/memberships/gyms/${selectedGymId}/purchase`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_id: selectedPlanId })
      })
      if (!r.ok) {
        const txt = await r.text().catch(() => '')
        throw new Error(txt || 'Failed to purchase membership')
      }
      const data = (await r.json()) as PurchaseMembershipResponse
      setPurchase({ status: 'ready', data })

      // Best UX: send user to Profile pass after purchase.
      navigate('/profile')
    } catch (e) {
      setPurchase({ status: 'error', message: e instanceof Error ? e.message : 'Unable to purchase membership' })
    }
  }

  return (
    <div className={styles.pageRoot}>
      <header className={styles.navbar}>
        <div>
          <a
            className={styles.logo}
            href="/"
            onClick={(e) => {
              e.preventDefault()
              navigate('/')
            }}
          >
            FitiGo
          </a>
        </div>

        <nav className={styles.navCenter} aria-label="Primary">
          <a
            className={styles.navItem}
            href="/nearby"
            onClick={(e) => {
              e.preventDefault()
              navigate('/nearby')
            }}
          >
            EXPLORE
          </a>
          <a
            className={`${styles.navItem} ${styles.navItemActive}`}
            href="/membership"
            onClick={(e) => {
              e.preventDefault()
              navigate('/membership')
            }}
          >
            MEMBERSHIP
          </a>
          <a
            className={styles.navItem}
            href="/classes"
            onClick={(e) => {
              e.preventDefault()
              navigate('/classes')
            }}
          >
            CLASSES
          </a>
        </nav>

        <div className={styles.navRight}>
          <button type="button" className={styles.getAppBtn} onClick={() => setAppOpen(true)}>
            Get the App
          </button>
          <ProfileIconButton className={styles.profileBtn} avatarClassName={styles.profileAvatar} />
        </div>
      </header>

      <main className={styles.content}>
        <div className={styles.container}>
          <div className={styles.pageHeader}>
            <h1 className={styles.pageTitle}>Membership</h1>
            <div className={styles.pageSub}>Select a membership: Multi Access or a specific gym plan.</div>
          </div>

          <div className={styles.modeTabs} role="tablist" aria-label="Membership type">
            <button
              type="button"
              className={`${styles.tabBtn} ${mode === 'multi' ? styles.tabBtnActive : ''}`}
              onClick={() => setMode('multi')}
              role="tab"
              aria-selected={mode === 'multi'}
            >
              Multi Access
            </button>
            <button
              type="button"
              className={`${styles.tabBtn} ${mode === 'single' ? styles.tabBtnActive : ''}`}
              onClick={() => setMode('single')}
              role="tab"
              aria-selected={mode === 'single'}
            >
              Specific Gym
            </button>
          </div>

          {mode === 'multi' ? (
            <section className={styles.card}>
            <div className={styles.cardHeader}>
              <div>
                <div className={styles.cardKicker}>MULTI-GYM MEMBERSHIP</div>
                <div className={styles.cardTitle}>One plan. Many partner gyms.</div>
                <div className={styles.cardDesc}>Select a duration and enjoy access across Fitigo partner gyms.</div>
              </div>
              <button type="button" className={styles.secondaryBtn} onClick={() => navigate('/nearby')}>
                Explore partner gyms
              </button>
            </div>

            <div className={styles.planGrid}>
              {MULTI_GYM_PLANS.map((p) => (
                <div key={p.key} className={styles.planCard}>
                  <div className={styles.planTitle}>{p.title}</div>
                  <div className={styles.planMeta}>
                    <span className={styles.pill}>{p.durationLabel}</span>
                    <span className={styles.price}>{p.priceLabel}</span>
                  </div>
                  <div className={styles.planSub}>{p.subLabel}</div>

                  <button
                    type="button"
                    className={styles.primaryBtn}
                    onClick={() => {
                      // Backend support for network-wide memberships is not implemented yet.
                      // Keep UX: prompt auth (if needed) then show a clear message.
                      if (!getAccessToken()) {
                        openAuthModal('multi_membership_interest')
                        return
                      }
                      setMultiNotice('Multi-access membership purchase is coming soon. For now, you can buy a specific gym membership below.')
                    }}
                  >
                    Choose Plan
                  </button>
                </div>
              ))}
            </div>

              {multiNotice ? <div className={styles.infoBanner}>{multiNotice}</div> : null}

              <div className={styles.benefitsWrap}>
                <div className={styles.benefitsTitle}>Benefits (Multi Access)</div>
                <ul className={styles.benefitsList}>
                  {MULTI_GYM_BENEFITS.map((b) => (
                    <li key={b} className={styles.benefitItem}>
                      {b}
                    </li>
                  ))}
                </ul>
                <div className={styles.note}>
                  Note: The current MVP backend supports purchasing membership plans that belong to a specific gym.
                  Network-wide multi-access plans require additional backend support.
                </div>
              </div>
            </section>
          ) : (
            <section className={styles.card}>
            <div className={styles.cardHeader}>
              <div>
                <div className={styles.cardKicker}>SPECIFIC GYM MEMBERSHIP</div>
                <div className={styles.cardTitle}>Subscribe to a single gym</div>
                <div className={styles.cardDesc}>Pick a gym, select a duration (monthly/quarterly/etc.), and activate access.</div>
              </div>
              <button type="button" className={styles.secondaryBtn} onClick={() => navigate('/nearby')}>
                Find gyms
              </button>
            </div>

              <div className={styles.fieldRow}>
              <label className={styles.label} htmlFor="gymSelect">
                Select Gym
              </label>
              {gyms.status === 'loading' || gyms.status === 'idle' ? (
                <div className={styles.skeletonLine} style={{ width: 260 }} />
              ) : gyms.status === 'error' ? (
                <div className={styles.errorMsg}>{gyms.message}</div>
              ) : (
                  <select
                    id="gymSelect"
                    className={styles.select}
                    value={selectedGymId ?? ''}
                    onChange={(e) => setSelectedGymId(Number(e.target.value))}
                  >
                    {gyms.data.map((g) => (
                      <option key={g.id} value={g.id}>
                        {g.name}
                        {g.city ? ` — ${g.city}` : ''}
                      </option>
                    ))}
                  </select>
              )}
            </div>

            <div className={styles.divider} />

            <div className={styles.planSection}>
              <div className={styles.sectionTitle}>Choose Duration</div>

              {plans.status === 'loading' || plans.status === 'idle' ? (
                <div className={styles.planGrid}>
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className={styles.planCard}>
                      <div className={styles.skeletonLine} style={{ width: 180 }} />
                      <div className={styles.skeletonLine} style={{ width: 110, marginTop: 10 }} />
                      <div className={styles.skeletonLine} style={{ width: 220, marginTop: 10 }} />
                    </div>
                  ))}
                </div>
              ) : plans.status === 'error' ? (
                <div className={styles.errorMsg}>{plans.message}</div>
              ) : plans.data.length === 0 ? (
                <div className={styles.note}>No active membership plans found for this gym.</div>
              ) : (
                <div className={styles.planGrid}>
                  {plans.data.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      className={`${styles.planPick} ${selectedPlanId === p.id ? styles.planPickActive : ''}`}
                      onClick={() => setSelectedPlanId(p.id)}
                    >
                      <div className={styles.planPickTitle}>{p.name}</div>
                      <div className={styles.planPickMeta}>
                        <span className={styles.pill}>{p.duration_days} days</span>
                        <span className={styles.price}>
                          {p.currency} {p.price}
                        </span>
                      </div>
                      <div className={styles.planPickDesc}>{p.description ?? 'Unlimited access during plan period.'}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>

              <div className={styles.checkoutRow}>
              <div className={styles.summary}>
                <div className={styles.summaryTitle}>Summary</div>
                <div className={styles.summaryLine}>
                  <span>Gym</span>
                  <span>{selectedGym?.name ?? '—'}</span>
                </div>
                <div className={styles.summaryLine}>
                  <span>Plan</span>
                  <span>{selectedPlan?.name ?? '—'}</span>
                </div>
                <div className={styles.summaryLine}>
                  <span>Price</span>
                  <span>{selectedPlan ? `${selectedPlan.currency} ${selectedPlan.price}` : '—'}</span>
                </div>

                {purchase.status === 'error' ? <div className={styles.errorMsg}>{purchase.message}</div> : null}
              </div>

              <button
                type="button"
                className={styles.primaryBtn}
                disabled={
                  purchase.status === 'loading' ||
                  !selectedGymId ||
                  !selectedPlanId ||
                  plans.status !== 'ready' ||
                  plans.data.length === 0
                }
                onClick={() => void handlePurchaseSingleGym()}
              >
                {purchase.status === 'loading' ? 'Activating…' : 'Subscribe Now'}
              </button>
            </div>
            </section>
          )}
        </div>
      </main>

      <AppDownloadModal open={appOpen} onClose={() => setAppOpen(false)} />
    </div>
  )
}
