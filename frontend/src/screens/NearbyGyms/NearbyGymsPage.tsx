import { useEffect, useMemo, useRef, useState } from 'react'
import styles from './nearbyGyms.module.css'
import { discoverGyms, fetchGymTypes } from './api'
import GymCard from './GymCard'
import SkeletonCard from './SkeletonCard'
import SupportWidget from './SupportWidget'
import LocationPickerModal from './LocationPickerModal'
import AppDownloadModal from './AppDownloadModal'
import { getStoredLocation, setStoredLocation } from './LocationStore'
import { useDebouncedValue } from './useDebouncedValue'
import type { GymDiscoverItem, LocationContext } from './types'
import { navigate } from '../../router'
import ProfileIconButton from '../../components/ProfileIconButton'

const DEFAULT_LOCATION: LocationContext = {
  location_name: 'Kukatpally',
  latitude: 17.4948,
  longitude: 78.3996,
  city: 'Hyderabad',
  state: 'Telangana',
  country: 'India'
}

function titleForLocation(name: string) {
  return `Gyms in ${name}: Find Your Perfect Workout Space`
}

export default function NearbyGymsPage() {
  // NOTE: This page currently maintains its own minimal auth/profile UI.
  // We wire the profile button to navigate to /profile for consistency with Home.
  const [location, setLocation] = useState<LocationContext>(() => getStoredLocation() ?? DEFAULT_LOCATION)
  const [locationOpen, setLocationOpen] = useState(false)
  const [appOpen, setAppOpen] = useState(false)

  const [types, setTypes] = useState<string[]>(['All Gym Types'])
  const [typeLoading, setTypeLoading] = useState(false)

  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search, 350)
  const [gymType, setGymType] = useState('All Gym Types')

  const [filtersOpen, setFiltersOpen] = useState(false)
  const [radiusKm, setRadiusKm] = useState(10)
  const [openNow, setOpenNow] = useState(false)
  const [minRating, setMinRating] = useState<number | null>(null)
  const [sortBy, setSortBy] = useState<'recommended' | 'distance' | 'rating'>('recommended')
  const [membershipAccess, setMembershipAccess] = useState<string | null>(null)

  const [gyms, setGyms] = useState<GymDiscoverItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const listKey = useMemo(() => {
    return JSON.stringify({
      location,
      debouncedSearch,
      gymType,
      radiusKm,
      openNow,
      minRating,
      sortBy,
      membershipAccess
    })
  }, [location, debouncedSearch, gymType, radiusKm, openNow, minRating, sortBy, membershipAccess])

  const sentinelRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    setStoredLocation(location)
  }, [location])

  useEffect(() => {
    setTypeLoading(true)
    fetchGymTypes()
      .then((items) => setTypes(items.length ? items : ['All Gym Types']))
      .catch(() => {
        // Keep minimal fallback
        setTypes(['All Gym Types'])
      })
      .finally(() => setTypeLoading(false))
  }, [])

  // Reset + load first page whenever filters change
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setPage(1)
    discoverGyms({
      latitude: location.latitude,
      longitude: location.longitude,
      radius_km: radiusKm,
      search: debouncedSearch || undefined,
      gym_type: gymType === 'All Gym Types' ? undefined : gymType,
      open_now: openNow || undefined,
      min_rating: minRating ?? undefined,
      membership_access: membershipAccess ?? undefined,
      sort_by: sortBy === 'recommended' ? undefined : sortBy,
      page: 1,
      page_size: 12
    })
      .then((res) => {
        if (cancelled) return
        setGyms(res.gyms)
        setTotal(res.total_count)
        setHasMore(res.has_more)
      })
      .catch((e) => {
        if (cancelled) return
        setError(e?.message ?? 'We could not load gyms right now.')
        setGyms([])
        setTotal(0)
        setHasMore(false)
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [listKey])

  // Infinite load when sentinel becomes visible
  useEffect(() => {
    if (!hasMore) return
    if (loading || loadingMore) return
    const el = sentinelRef.current
    if (!el) return

    const io = new IntersectionObserver(
      (entries) => {
        const first = entries[0]
        if (!first?.isIntersecting) return

        setLoadingMore(true)
        const nextPage = page + 1
        discoverGyms({
          latitude: location.latitude,
          longitude: location.longitude,
          radius_km: radiusKm,
          search: debouncedSearch || undefined,
          gym_type: gymType === 'All Gym Types' ? undefined : gymType,
          open_now: openNow || undefined,
          min_rating: minRating ?? undefined,
          membership_access: membershipAccess ?? undefined,
          sort_by: sortBy === 'recommended' ? undefined : sortBy,
          page: nextPage,
          page_size: 12
        })
          .then((res) => {
            setGyms((prev) => [...prev, ...res.gyms])
            setTotal(res.total_count)
            setHasMore(res.has_more)
            setPage(nextPage)
          })
          .catch(() => {
            // keep existing list
          })
          .finally(() => setLoadingMore(false))
      },
      { root: null, rootMargin: '220px 0px', threshold: 0 }
    )

    io.observe(el)
    return () => io.disconnect()
  }, [hasMore, loading, loadingMore, page, listKey])

  const headerTitle = titleForLocation(location.location_name)

  return (
    <div className={styles.pageRoot}>
      <header className={styles.navbar}>
        <div className={styles.navLeft}>
          <a className={styles.logo} href="/">
            FitiGo
          </a>
        </div>

        <nav className={styles.navCenter} aria-label="Primary">
          <a className={`${styles.navItem} ${styles.navItemActive}`} href="/nearby">
            GYMS
          </a>
        </nav>

        <div className={styles.navRight}>
          <button type="button" className={styles.locationPill} onClick={() => setLocationOpen(true)}>
            <span aria-hidden="true">📍</span>
            <span style={{ fontWeight: 650 }}>{location.location_name}</span>
          </button>

          <button type="button" className={styles.getAppBtn} onClick={() => setAppOpen(true)}>
            Get the App
          </button>

          <ProfileIconButton className={styles.profileBtn} avatarClassName={styles.profileAvatar} />
        </div>
      </header>

      <main className={styles.content}>
        <div className={styles.headerRow}>
          <div className={styles.headerLeft}>
            <h1 className={styles.pageTitle}>{headerTitle}</h1>
          </div>

          <div className={styles.headerRight}>
            <div className={styles.searchWrap}>
              <span className={styles.searchIcon} aria-hidden="true">
                ⌕
              </span>
              <input
                className={styles.searchInput}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by gym name"
                aria-label="Search by gym name"
              />
              {search ? (
                <button type="button" className={styles.clearBtn} onClick={() => setSearch('')} aria-label="Clear search">
                  ×
                </button>
              ) : null}
              {loading ? <span className={styles.searchSpinner} aria-hidden="true" /> : null}
            </div>

            <div className={styles.selectWrap}>
              <span className={styles.filterIcon} aria-hidden="true">
                ⛭
              </span>
              <select
                className={styles.select}
                value={gymType}
                onChange={(e) => setGymType(e.target.value)}
                aria-label="Gym type"
                disabled={typeLoading}
              >
                {types.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>

            <button type="button" className={styles.filtersBtn} onClick={() => setFiltersOpen((v) => !v)}>
              Filters
            </button>
          </div>
        </div>

        {filtersOpen ? (
          <div className={styles.advancedFilters} role="region" aria-label="Advanced filters">
            <div className={styles.filtersGrid}>
              <div className={styles.filterBlock}>
                <div className={styles.filterLabel}>Distance</div>
                <div className={styles.chipsRow}>
                  {[1, 3, 5, 10].map((v) => (
                    <button
                      key={v}
                      type="button"
                      className={`${styles.chip} ${radiusKm === v ? styles.chipActive : ''}`}
                      onClick={() => setRadiusKm(v)}
                    >
                      Within {v} km
                    </button>
                  ))}
                  <button
                    type="button"
                    className={`${styles.chip} ${radiusKm === 15 ? styles.chipActive : ''}`}
                    onClick={() => setRadiusKm(15)}
                  >
                    Within 15 km
                  </button>
                </div>
              </div>

              <div className={styles.filterBlock}>
                <div className={styles.filterLabel}>Open Now</div>
                <label className={styles.toggle}>
                  <input type="checkbox" checked={openNow} onChange={(e) => setOpenNow(e.target.checked)} />
                  <span>Open Now</span>
                </label>
              </div>

              <div className={styles.filterBlock}>
                <div className={styles.filterLabel}>Rating</div>
                <div className={styles.chipsRow}>
                  {[4.5, 4.0, 3.5].map((v) => (
                    <button
                      key={v}
                      type="button"
                      className={`${styles.chip} ${minRating === v ? styles.chipActive : ''}`}
                      onClick={() => setMinRating(v)}
                    >
                      {v}+
                    </button>
                  ))}
                  <button type="button" className={`${styles.chip} ${minRating == null ? styles.chipActive : ''}`} onClick={() => setMinRating(null)}>
                    Any
                  </button>
                </div>
              </div>

              <div className={styles.filterBlock}>
                <div className={styles.filterLabel}>Membership</div>
                <div className={styles.chipsRow}>
                  <button
                    type="button"
                    className={`${styles.chip} ${membershipAccess == null ? styles.chipActive : ''}`}
                    onClick={() => setMembershipAccess(null)}
                  >
                    All
                  </button>
                  <button
                    type="button"
                    className={`${styles.chip} ${membershipAccess === 'INCLUDED' ? styles.chipActive : ''}`}
                    onClick={() => setMembershipAccess('INCLUDED')}
                  >
                    Included
                  </button>
                  <button
                    type="button"
                    className={`${styles.chip} ${membershipAccess === 'NO_ACTIVE_MEMBERSHIP' ? styles.chipActive : ''}`}
                    onClick={() => setMembershipAccess('NO_ACTIVE_MEMBERSHIP')}
                  >
                    Needs Membership
                  </button>
                </div>
              </div>

              <div className={styles.filterBlock}>
                <div className={styles.filterLabel}>Sort</div>
                <div className={styles.chipsRow}>
                  <button type="button" className={`${styles.chip} ${sortBy === 'recommended' ? styles.chipActive : ''}`} onClick={() => setSortBy('recommended')}>
                    Recommended
                  </button>
                  <button type="button" className={`${styles.chip} ${sortBy === 'distance' ? styles.chipActive : ''}`} onClick={() => setSortBy('distance')}>
                    Nearest
                  </button>
                  <button type="button" className={`${styles.chip} ${sortBy === 'rating' ? styles.chipActive : ''}`} onClick={() => setSortBy('rating')}>
                    Highest Rated
                  </button>
                </div>
              </div>
            </div>
          </div>
        ) : null}

        <div className={styles.resultsTabRow}>
          <div className={styles.resultsTabActive}>Gyms ({total})</div>
          <div className={styles.resultsTabDivider} />
        </div>

        {error ? (
          <div className={styles.errorState} role="alert">
            <div style={{ fontWeight: 700, marginBottom: 6 }}>We couldn't load gyms right now.</div>
            <div style={{ color: 'var(--muted)', marginBottom: 12 }}>{error}</div>
            <button type="button" className={styles.retryBtn} onClick={() => window.location.reload()}>
              Try Again
            </button>
          </div>
        ) : null}

        {!error && !loading && gyms.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.emptyTitle}>No gyms found nearby</div>
            <div className={styles.emptySub}>Try expanding your search radius or choosing a different location.</div>
            <div className={styles.emptyActions}>
              <button type="button" className={styles.retryBtn} onClick={() => setRadiusKm((v) => Math.min(25, v + 5))}>
                Expand Search Radius
              </button>
              <button type="button" className={styles.ghostAction} onClick={() => setLocationOpen(true)}>
                Change Location
              </button>
              <button
                type="button"
                className={styles.ghostAction}
                onClick={() => {
                  setSearch('')
                  setGymType('All Gym Types')
                  setFiltersOpen(false)
                  setRadiusKm(10)
                  setOpenNow(false)
                  setMinRating(null)
                  setMembershipAccess(null)
                  setSortBy('recommended')
                }}
              >
                Clear Filters
              </button>
            </div>
          </div>
        ) : null}

        <div className={styles.grid} aria-busy={loading ? 'true' : 'false'}>
          {loading
            ? Array.from({ length: 9 }).map((_, idx) => <SkeletonCard key={`sk-${idx}`} />)
            : gyms.map((g) => <GymCard key={g.gym_id} gym={g} />)}
          {loadingMore ? Array.from({ length: 3 }).map((_, idx) => <SkeletonCard key={`skm-${idx}`} />) : null}
        </div>

        {hasMore && !loading ? (
          <div className={styles.loadMoreRow}>
            <button
              type="button"
              className={styles.loadMoreBtn}
              disabled={loadingMore}
              onClick={() => {
                // manual load more (in addition to IO)
                if (loadingMore) return
                setLoadingMore(true)
                const nextPage = page + 1
                discoverGyms({
                  latitude: location.latitude,
                  longitude: location.longitude,
                  radius_km: radiusKm,
                  search: debouncedSearch || undefined,
                  gym_type: gymType === 'All Gym Types' ? undefined : gymType,
                  open_now: openNow || undefined,
                  min_rating: minRating ?? undefined,
                  membership_access: membershipAccess ?? undefined,
                  sort_by: sortBy === 'recommended' ? undefined : sortBy,
                  page: nextPage,
                  page_size: 12
                })
                  .then((res) => {
                    setGyms((prev) => [...prev, ...res.gyms])
                    setTotal(res.total_count)
                    setHasMore(res.has_more)
                    setPage(nextPage)
                  })
                  .finally(() => setLoadingMore(false))
              }}
            >
              {loadingMore ? 'Loading…' : 'Load more results'}
            </button>
          </div>
        ) : null}

        <div ref={sentinelRef} />
      </main>

      <SupportWidget />

      <LocationPickerModal
        open={locationOpen}
        value={location}
        onChange={(loc) => setLocation(loc)}
        onClose={() => setLocationOpen(false)}
      />
      <AppDownloadModal open={appOpen} onClose={() => setAppOpen(false)} />
    </div>
  )
}
