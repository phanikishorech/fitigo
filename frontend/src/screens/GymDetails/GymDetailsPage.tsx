import { useEffect, useMemo, useState } from 'react'
import styles from './gymDetails.module.css'
import { fetchGymDetails, fetchGymMembershipPlans, purchaseGymMembershipPlan } from './api'
import type { GymDetailsImage, GymDetailsResponse, GymMembershipPlan } from './types'
import AppDownloadModal from '../NearbyGyms/AppDownloadModal'
import SupportWidget from '../NearbyGyms/SupportWidget'
import { navigate } from '../../router'
import ProfileIconButton from '../../components/ProfileIconButton'
import { getAccessToken } from '../../auth'
import { openAuthModal } from '../../authUi'

type AsyncState<T> =
  | { status: 'idle' | 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string }

function badgeForAccess(status: string) {
  switch (status) {
    case 'INCLUDED':
      return { cta: 'Access This Gym', sub: 'Included in your plan ✓', tag: 'Included in Your Plan ✓' }
    case 'UPGRADE_REQUIRED':
      return { cta: 'Upgrade to Access', sub: 'Your current plan does not include this gym.', tag: 'Upgrade Required' }
    case 'DAY_PASS_AVAILABLE':
      return { cta: 'Buy Day Pass', sub: 'Get single-visit access without a membership.', tag: 'Day Pass Available' }
    case 'UNAVAILABLE':
      return { cta: 'Currently Unavailable', sub: 'This gym is temporarily unavailable.', tag: 'Unavailable' }
    case 'NO_ACTIVE_MEMBERSHIP':
    default:
      return {
        cta: 'Book Now',
        sub: 'Get access to this gym and other partner gyms with one membership.',
        tag: 'Membership Required'
      }
  }
}

function dayName(dow: number) {
  return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][dow] ?? String(dow)
}

function fmtDateRange(startIso: string, endIso: string) {
  const s = new Date(startIso)
  const e = new Date(endIso)
  const opts: Intl.DateTimeFormatOptions = { hour: 'numeric', minute: '2-digit' }
  const dOpts: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short' }
  return `${s.toLocaleDateString(undefined, dOpts)}, ${s.toLocaleTimeString(undefined, opts)} - ${e.toLocaleTimeString(undefined, opts)}`
}

function iconForFacility(icon: string | null | undefined) {
  // Minimal icon mapping; keep small.
  switch (icon) {
    case 'dumbbell':
      return '🏋️'
    case 'heart':
      return '❤️'
    case 'lotus':
      return '🧘'
    case 'parking':
      return '🅿️'
    case 'shower':
      return '🚿'
    default:
      return '•'
  }
}

function Gallery({ images, gymName }: { images: GymDetailsImage[]; gymName: string }) {
  const [idx, setIdx] = useState(0)
  const safeImages = images.length ? images : [{ image_id: 0, image_url: '', alt_text: gymName, display_order: 0 }]

  const active = safeImages[Math.min(idx, safeImages.length - 1)]
  const canNav = safeImages.length > 1

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!canNav) return
      if (e.key === 'ArrowLeft') setIdx((v) => (v - 1 + safeImages.length) % safeImages.length)
      if (e.key === 'ArrowRight') setIdx((v) => (v + 1) % safeImages.length)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [canNav, safeImages.length])

  return (
    <div className={styles.gallery} aria-label="Gym image gallery">
      {active.image_url ? (
        <img className={styles.galleryMain} src={active.image_url} alt={active.alt_text ?? gymName} />
      ) : (
        <div className={styles.galleryMain} style={{ background: '#eef2f7' }} />
      )}

      {safeImages.length > 1 ? (
        <>
          <div className={styles.galleryDots} aria-label="Gallery thumbnails">
            {safeImages.slice(0, 6).map((im, i) => (
              <button
                key={`${im.image_id}-${i}`}
                type="button"
                className={`${styles.dot} ${i === idx ? styles.dotActive : ''}`}
                aria-label={`View image ${i + 1}`}
                onClick={() => setIdx(i)}
              />
            ))}
          </div>
        </>
      ) : null}
    </div>
  )
}

export default function GymDetailsPage({ gymId }: { gymId: number }) {
  const [appOpen, setAppOpen] = useState(false)
  const [data, setData] = useState<GymDetailsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hoursOpen, setHoursOpen] = useState(false)

  // gym-level membership plans
  const [plans, setPlans] = useState<AsyncState<GymMembershipPlan[]>>({ status: 'idle' })
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null)
  const [purchaseState, setPurchaseState] = useState<AsyncState<null>>({ status: 'idle' })

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchGymDetails(gymId)
      .then((d) => {
        if (!cancelled) setData(d)
      })
      .catch((e) => {
        if (!cancelled) setError(e?.message ?? 'Failed to load gym')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [gymId])

  useEffect(() => {
    let cancelled = false
    setPlans({ status: 'loading' })
    setSelectedPlanId(null)
    setPurchaseState({ status: 'idle' })
    fetchGymMembershipPlans(gymId)
      .then((d) => {
        if (cancelled) return
        const active = (d ?? []).filter((p) => p.is_active)
        setPlans({ status: 'ready', data: active })
        if (active.length === 1) setSelectedPlanId(active[0].id)
      })
      .catch((e) => {
        if (cancelled) return
        setPlans({ status: 'error', message: e?.message ?? 'Failed to load membership plans' })
      })
    return () => {
      cancelled = true
    }
  }, [gymId])

  const selectedPlan = useMemo(() => {
    if (plans.status !== 'ready') return null
    return plans.data.find((p) => p.id === selectedPlanId) ?? null
  }, [plans, selectedPlanId])

  const handlePurchase = async () => {
    if (!selectedPlanId) return
    const token = getAccessToken()
    if (!token) {
      openAuthModal('gym_details_membership_purchase')
      return
    }

    setPurchaseState({ status: 'loading' })
    try {
      await purchaseGymMembershipPlan(gymId, selectedPlanId)
      setPurchaseState({ status: 'ready', data: null })
      navigate(`/gyms/${gymId}/access`)
    } catch (e: any) {
      setPurchaseState({ status: 'error', message: e?.message ?? 'Failed to purchase membership' })
    }
  }

  const crumbs = useMemo(() => {
    const city = data?.location?.city ?? 'City'
    const locality = data?.location?.locality ?? 'Locality'
    const name = data?.gym_name ?? 'Gym'
    return { city, locality, name }
  }, [data?.gym_name, data?.location?.city, data?.location?.locality])

  const access = badgeForAccess(data?.membership_access?.status ?? 'NO_ACTIVE_MEMBERSHIP')
  const hasActiveGymMembership = (data?.membership_access?.status ?? '') === 'INCLUDED'

  const mapUrl = useMemo(() => {
    const lat = data?.location?.latitude
    const lon = data?.location?.longitude
    if (typeof lat !== 'number' || typeof lon !== 'number') return null
    const bbox = `${lon - 0.01},${lat - 0.005},${lon + 0.01},${lat + 0.005}`
    return `https://www.openstreetmap.org/export/embed.html?bbox=${encodeURIComponent(bbox)}&layer=mapnik&marker=${lat},${lon}`
  }, [data?.location?.latitude, data?.location?.longitude])

  const googleMapsLink = useMemo(() => {
    const lat = data?.location?.latitude
    const lon = data?.location?.longitude
    if (typeof lat !== 'number' || typeof lon !== 'number') return null
    return `https://www.google.com/maps?q=${lat},${lon}`
  }, [data?.location?.latitude, data?.location?.longitude])

  return (
    <div className={styles.pageRoot}>
      <header className={styles.navbar}>
        <div>
          <a className={styles.logo} href="/" onClick={(e) => { e.preventDefault(); navigate('/') }}>
            FitiGo
          </a>
        </div>
        <nav className={styles.navCenter} aria-label="Primary">
          <a className={`${styles.navItem} ${styles.navItemActive}`} href="/nearby" onClick={(e) => { e.preventDefault(); navigate('/nearby') }}>
            EXPLORE
          </a>
          <a className={styles.navItem} href="/membership" onClick={(e) => { e.preventDefault(); navigate('/membership') }}>
            MEMBERSHIP
          </a>
          <a className={styles.navItem} href="/classes" onClick={(e) => { e.preventDefault(); navigate('/classes') }}>
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
          {loading ? (
            <div className={styles.grid}>
              <div>
                <div className={`${styles.skeleton} ${styles.skeletonLine}`} style={{ width: 260, marginBottom: 12 }} />
                <div className={`${styles.skeleton} ${styles.skeletonLine}`} style={{ width: '70%', height: 26, borderRadius: 10 }} />
                <div className={`${styles.skeleton} ${styles.skeletonLine}`} style={{ width: 360, marginTop: 12 }} />
                <div className={styles.gallery} style={{ marginTop: 16 }}>
                  <div className={styles.galleryMain} style={{ background: '#eef2f7' }} />
                </div>
                <div className={styles.card} style={{ marginTop: 16 }}>
                  <div className={`${styles.skeleton} ${styles.skeletonLine}`} style={{ width: 220 }} />
                  <div className={`${styles.skeleton} ${styles.skeletonLine}`} style={{ width: '100%', marginTop: 10 }} />
                  <div className={`${styles.skeleton} ${styles.skeletonLine}`} style={{ width: '90%', marginTop: 10 }} />
                </div>
              </div>
              <div className={styles.sidebar}>
                <div className={styles.sidebarInner}>
                  <div className={styles.ctaCard}>
                    <div className={`${styles.skeleton} ${styles.skeletonLine}`} style={{ height: 48, borderRadius: 12 }} />
                    <div className={`${styles.skeleton} ${styles.skeletonLine}`} style={{ marginTop: 12 }} />
                    <div className={`${styles.skeleton} ${styles.skeletonLine}`} style={{ width: 200, marginTop: 12 }} />
                  </div>
                  <div className={styles.card}>
                    <div className={`${styles.skeleton} ${styles.skeletonLine}`} style={{ width: 160 }} />
                    <div className={`${styles.skeleton} ${styles.skeletonLine}`} style={{ width: '100%', marginTop: 10 }} />
                    <div className={`${styles.skeleton} ${styles.skeletonLine}`} style={{ width: '70%', marginTop: 10 }} />
                  </div>
                </div>
              </div>
            </div>
          ) : error || !data ? (
            <div className={styles.card}>
              <div className={styles.sectionTitle}>We couldn't load this gym</div>
              <div className={styles.muted}>{error ?? 'Please check your connection and try again.'}</div>
              <div style={{ display: 'flex', gap: 10, marginTop: 14, flexWrap: 'wrap' }}>
                <button type="button" className={styles.secondaryBtn} onClick={() => window.location.reload()}>
                  Try Again
                </button>
                <button type="button" className={styles.secondaryBtn} onClick={() => navigate('/nearby')}>
                  Back to Gyms
                </button>
              </div>
            </div>
          ) : (
            <div className={styles.grid}>
              <div>
                <div className={styles.breadcrumb} aria-label="Breadcrumb">
                  <a href="/nearby" onClick={(e) => { e.preventDefault(); navigate('/nearby') }}>
                    Gyms
                  </a>
                  <span aria-hidden="true">›</span>
                  <a href="/nearby" onClick={(e) => { e.preventDefault(); navigate('/nearby') }}>
                    {crumbs.city}
                  </a>
                  <span aria-hidden="true">›</span>
                  <a href="/nearby" onClick={(e) => { e.preventDefault(); navigate('/nearby') }}>
                    {crumbs.locality}
                  </a>
                  <span aria-hidden="true">›</span>
                  <span>{crumbs.name}</span>
                </div>

                <h1 className={styles.title}>{data.gym_name}</h1>
                <div className={styles.subRow}>
                  <span style={{ fontWeight: 750 }}>{data.location.locality ?? 'Nearby'}</span>
                  <span aria-hidden="true">•</span>
                  <span className={styles.rating}>
                    <span className={styles.star} aria-hidden="true">
                      ★
                    </span>
                    <span style={{ color: '#0f172a' }}>{data.ratings.average_rating != null ? data.ratings.average_rating.toFixed(1) : 'New'}</span>
                    <span style={{ color: '#64748b' }}>({data.ratings.review_count} ratings)</span>
                  </span>
                  <button
                    type="button"
                    className={styles.rateBtn}
                    onClick={() => window.alert('Rating flow will be enabled after auth + eligibility rules.')}
                  >
                    {data.ratings.user_rating ? `Your rating: ★ ${data.ratings.user_rating}` : 'Rate Gym'}
                  </button>
                </div>

                <div style={{ marginTop: 16 }}>
                  <Gallery images={data.images} gymName={data.gym_name} />
                </div>

                <section className={styles.card} style={{ marginTop: 16 }} aria-label="Workout options">
                  <h2 className={styles.sectionTitle}>Workout Options Available</h2>
                  <div className={styles.muted} style={{ marginBottom: 12 }}>
                    Click an option to explore available facilities and classes
                  </div>
                  <div className={styles.gridCards}>
                    {(data.workout_options ?? []).map((w) => (
                      <button
                        key={w.workout_type_id}
                        type="button"
                        className={styles.miniCard}
                        onClick={() => window.alert('Workout details are not wired yet (backend can expand later).')}
                        style={{ cursor: 'pointer' }}
                        aria-label={`View ${w.workout_type_name}`}
                      >
                        <div className={styles.miniIcon} aria-hidden="true">
                          {iconForFacility(w.icon)}
                        </div>
                        <div>
                          <div className={styles.miniTitle}>{w.workout_type_name}</div>
                          <div className={styles.muted} style={{ fontSize: 12, marginTop: 3 }}>
                            {w.access_type === 'INCLUDED' ? 'Included ✓' : w.access_type}
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                </section>

                <section className={styles.card} style={{ marginTop: 16 }} aria-label="Amenities">
                  <h2 className={styles.sectionTitle}>Amenities</h2>
                  {data.amenities?.length ? (
                    <div className={styles.amenitiesGrid}>
                      {data.amenities.map((a) => (
                        <div key={a.amenity_id} className={styles.amenity}>
                          <span className={styles.check} aria-hidden="true">
                            ✓
                          </span>
                          <span>{a.amenity_name}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className={styles.muted}>Amenities data is not available yet.</div>
                  )}
                </section>

                <section className={styles.card} style={{ marginTop: 16 }} aria-label="About this gym">
                  <h2 className={styles.sectionTitle}>About This Gym</h2>
                  <div className={styles.muted}>{data.description}</div>
                  {data.important_information?.length ? (
                    <ul className={styles.muted} style={{ marginTop: 12, paddingLeft: 18 }}>
                      {data.important_information.map((x, i) => (
                        <li key={i}>{x}</li>
                      ))}
                    </ul>
                  ) : null}
                </section>

                {data.rules?.length ? (
                  <section className={styles.card} style={{ marginTop: 16 }} aria-label="Gym rules">
                    <h2 className={styles.sectionTitle}>Gym Rules</h2>
                    <ul className={styles.muted} style={{ margin: 0, paddingLeft: 18 }}>
                      {data.rules.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </section>
                ) : null}

                <section className={styles.card} style={{ marginTop: 16 }} aria-label="Classes and activities nearby">
                  <h2 className={styles.sectionTitle}>Classes and Activities Nearby</h2>
                  {data.classes_nearby?.length ? (
                    <div className={styles.hScroll}>
                      {data.classes_nearby.map((c) => (
                        <div key={c.class_id} className={styles.hCard}>
                          <div
                            className={`${styles.badge} ${c.status === 'FULL' ? styles.badgeRed : styles.badgeGreen}`}
                            style={{ marginBottom: 10 }}
                          >
                            {c.kind} • {c.status}
                          </div>
                          <div style={{ fontWeight: 900, letterSpacing: -0.2 }}>{c.title}</div>
                          <div className={styles.muted} style={{ marginTop: 6 }}>
                            {c.gym_name}
                          </div>
                          <div className={styles.muted} style={{ marginTop: 8, fontSize: 13 }}>
                            {fmtDateRange(c.start_at, c.end_at)}
                          </div>
                          <div className={styles.muted} style={{ marginTop: 8, fontSize: 13 }}>
                            {c.filled} / {c.capacity} spots filled
                            {c.level ? ` • ${c.level}` : ''}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className={styles.muted}>No classes are listed for this gym yet.</div>
                  )}
                </section>

                <section className={styles.card} style={{ marginTop: 16 }} aria-label="Related gyms">
                  <h2 className={styles.sectionTitle}>Related Gyms Near {data.location.locality ?? 'You'}</h2>
                  {data.related_gyms?.length ? (
                    <div className={styles.relatedList}>
                      {data.related_gyms.map((g) => (
                        <a
                          key={g.gym_id}
                          href={`/gyms/${g.gym_id}`}
                          className={styles.relatedItem}
                          onClick={(e) => {
                            e.preventDefault()
                            navigate(`/gyms/${g.gym_id}`)
                          }}
                        >
                          {g.primary_image ? (
                            <img className={styles.relatedImg} src={g.primary_image} alt={g.gym_name} />
                          ) : (
                            <div className={styles.relatedImg} style={{ background: '#eef2f7' }} />
                          )}
                          <div>
                            <div style={{ fontWeight: 900 }}>{g.gym_name}</div>
                            <div className={styles.muted} style={{ fontSize: 13, marginTop: 4 }}>
                              {[g.locality, g.distance_km != null ? `${g.distance_km.toFixed(g.distance_km < 10 ? 1 : 0)} km` : null]
                                .filter(Boolean)
                                .join(' • ')}
                            </div>
                          </div>
                        </a>
                      ))}
                    </div>
                  ) : (
                    <div className={styles.muted}>No related gyms found.</div>
                  )}
                </section>

                <section className={styles.card} style={{ marginTop: 16 }} aria-label="Member reviews">
                  <h2 className={styles.sectionTitle}>Member Reviews</h2>
                  <div className={styles.muted} style={{ marginBottom: 12 }}>
                    {data.ratings.average_rating != null ? (
                      <>
                        <span style={{ fontWeight: 900, color: '#0f172a' }}>★ {data.ratings.average_rating.toFixed(1)}</span> based on{' '}
                        <span style={{ fontWeight: 850, color: '#0f172a' }}>{data.ratings.review_count}</span> reviews
                      </>
                    ) : (
                      'No reviews yet.'
                    )}
                  </div>

                  {data.reviews?.length ? (
                    <div style={{ display: 'grid', gap: 10 }}>
                      {data.reviews.map((r) => (
                        <div key={r.review_id} style={{ border: '1px solid var(--line)', borderRadius: 12, padding: 12 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                            <div style={{ fontWeight: 900 }}>{r.user_display_name}</div>
                            <div style={{ fontWeight: 900, color: '#0f172a' }}>★ {r.rating}</div>
                          </div>
                          {r.comment ? <div className={styles.muted} style={{ marginTop: 8 }}>{r.comment}</div> : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className={styles.muted}>No reviews are available for this gym yet.</div>
                  )}

                  <button
                    type="button"
                    className={styles.linkBtn}
                    style={{ marginTop: 12 }}
                    onClick={() => window.alert('View all reviews is not wired yet.')}
                  >
                    View All Reviews
                  </button>
                </section>
              </div>

              <div className={styles.sidebar}>
                <div className={styles.sidebarInner}>
                  <div className={styles.ctaCard}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'baseline' }}>
                      <div style={{ fontWeight: 950, color: '#0f172a' }}>{hasActiveGymMembership ? 'Your Membership' : 'Membership Plans'}</div>
                      <a
                        href={`/membership?gymId=${gymId}`}
                        className={styles.linkBtn}
                        onClick={(e) => {
                          e.preventDefault()
                          navigate(`/membership?gymId=${gymId}`)
                        }}
                        style={{ fontSize: 12 }}
                      >
                        {hasActiveGymMembership ? 'Manage' : 'View all'}
                      </a>
                    </div>

                    {hasActiveGymMembership ? (
                      <>
                        <div className={styles.muted} style={{ marginTop: 10 }}>
                          {data.membership_access.current_plan
                            ? `Active: ${data.membership_access.current_plan}`
                            : 'Your membership is active for this gym.'}
                        </div>
                        <div style={{ marginTop: 12, display: 'grid', gap: 10 }}>
                          <button
                            type="button"
                            className={styles.primaryBtn}
                            onClick={() => navigate(`/gyms/${gymId}/access`)}
                            disabled={data.membership_access.status === 'UNAVAILABLE'}
                          >
                            Access This Gym
                          </button>
                          <button type="button" className={styles.secondaryBtn} onClick={() => navigate('/profile')}>
                            View in Profile
                          </button>
                        </div>
                      </>
                    ) : plans.status === 'loading' || plans.status === 'idle' ? (
                      <div style={{ marginTop: 10, display: 'grid', gap: 10 }}>
                        <div className={`${styles.skeleton} ${styles.skeletonLine}`} style={{ height: 56, borderRadius: 12 }} />
                        <div className={`${styles.skeleton} ${styles.skeletonLine}`} style={{ height: 56, borderRadius: 12 }} />
                      </div>
                    ) : plans.status === 'error' ? (
                      <div className={styles.muted} style={{ marginTop: 10 }}>
                        {plans.message}
                      </div>
                    ) : plans.data.length === 0 ? (
                      <div className={styles.muted} style={{ marginTop: 10 }}>
                        No membership plans available for this gym right now.
                      </div>
                    ) : (
                      <div style={{ marginTop: 10, display: 'grid', gap: 10 }}>
                        {plans.data.slice(0, 3).map((p) => (
                          <button
                            key={p.id}
                            type="button"
                            className={`${styles.planPick} ${selectedPlanId === p.id ? styles.planPickActive : ''}`}
                            onClick={() => setSelectedPlanId(p.id)}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                              <div style={{ fontWeight: 950 }}>{p.name}</div>
                              <div style={{ fontWeight: 950, color: '#0f172a' }}>
                                {p.currency} {p.price}
                              </div>
                            </div>
                            <div className={styles.muted} style={{ fontSize: 12, marginTop: 4 }}>
                              {p.duration_days} days • {p.description ?? 'Unlimited access during plan period.'}
                            </div>
                          </button>
                        ))}

                        {purchaseState.status === 'error' ? (
                          <div className={styles.muted} style={{ color: '#b91c1c', fontWeight: 800 }}>
                            {purchaseState.message}
                          </div>
                        ) : null}

                        <button
                          type="button"
                          className={styles.primaryBtn}
                          onClick={() => void handlePurchase()}
                          disabled={purchaseState.status === 'loading' || !selectedPlanId || data.membership_access.status === 'UNAVAILABLE'}
                          style={{ marginTop: 6 }}
                        >
                          {purchaseState.status === 'loading'
                            ? 'Activating…'
                            : selectedPlan
                              ? `Subscribe • ${selectedPlan.currency} ${selectedPlan.price}`
                              : 'Subscribe'}
                        </button>

                        <button
                          type="button"
                          className={styles.secondaryBtn}
                          onClick={() => navigate(`/gyms/${gymId}/access`)}
                          disabled={data.membership_access.status === 'UNAVAILABLE'}
                        >
                          Proceed to booking
                        </button>
                      </div>
                    )}

                    <div className={styles.ctaSub} style={{ marginTop: 10 }}>
                      {access.sub}
                    </div>

                    <div className={styles.ctaMeta}>
                      <span className={styles.ctaTag}>{access.tag}</span>
                    </div>

                    <div className={styles.secondaryRow}>
                      <button
                        type="button"
                        className={styles.secondaryBtn}
                        onClick={async () => {
                          const url = window.location.href
                          try {
                            if (navigator.share) {
                              await navigator.share({ title: data.gym_name, url })
                            } else {
                              await navigator.clipboard.writeText(url)
                              window.alert('Link copied')
                            }
                          } catch {
                            // ignore
                          }
                        }}
                      >
                        Share
                      </button>
                      <button
                        type="button"
                        className={styles.secondaryBtn}
                        onClick={() => window.alert('Corporate Fitness enquiry flow not wired yet.')}
                      >
                        Corporate Fitness
                      </button>
                    </div>
                  </div>

                  <div className={styles.card}>
                    <h3 className={styles.sectionTitle}>Opening Hours</h3>
                    <div className={styles.hoursRow}>
                      <div style={{ fontWeight: 850 }}>{data.opening_hours.open_today ?? 'Hours not available'}</div>
                      {data.opening_hours.open_now == null ? null : data.opening_hours.open_now ? (
                        <span className={styles.pillOpen}>Open Now</span>
                      ) : (
                        <span className={styles.pillClosed}>Closed</span>
                      )}
                    </div>
                    <button type="button" className={styles.linkBtn} style={{ marginTop: 10 }} onClick={() => setHoursOpen((v) => !v)}>
                      {hoursOpen ? 'Hide Hours' : 'View Hours'}
                    </button>
                    {hoursOpen ? (
                      <div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
                        {data.opening_hours.weekly.map((h) => (
                          <div key={h.day_of_week} style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                            <div className={styles.muted} style={{ fontWeight: 800 }}>
                              {dayName(h.day_of_week)}
                            </div>
                            <div className={styles.muted}>
                              {h.is_closed ? 'Closed' : `${h.open_time ?? ''} - ${h.close_time ?? ''}`}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>

                  <div className={styles.card}>
                    <h3 className={styles.sectionTitle}>Location</h3>
                    <div className={styles.muted} style={{ marginBottom: 10 }}>
                      {data.location.full_address ?? 'Address not available'}
                    </div>
                    {mapUrl ? (
                      <iframe className={styles.mapFrame} title="Map" src={mapUrl} loading="lazy" />
                    ) : (
                      <div className={styles.mapFrame} style={{ display: 'grid', placeItems: 'center', color: '#64748b' }}>
                        Map not available
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 10, marginTop: 12, flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        className={styles.secondaryBtn}
                        onClick={() => {
                          if (googleMapsLink) window.open(googleMapsLink, '_blank')
                        }}
                        disabled={!googleMapsLink}
                      >
                        Open in Maps
                      </button>
                      <button
                        type="button"
                        className={styles.secondaryBtn}
                        onClick={() => {
                          if (googleMapsLink) window.open(googleMapsLink + '&navigate=yes', '_blank')
                        }}
                        disabled={!googleMapsLink}
                      >
                        Get Directions
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>

      <SupportWidget />
      <AppDownloadModal open={appOpen} onClose={() => setAppOpen(false)} />
    </div>
  )
}
