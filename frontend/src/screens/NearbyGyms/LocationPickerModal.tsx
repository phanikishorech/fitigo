import { useEffect, useMemo, useRef, useState } from 'react'
import styles from './nearbyGyms.module.css'
import type { LocationContext } from './types'
import { useDebouncedValue } from './useDebouncedValue'

type Props = {
  open: boolean
  value: LocationContext
  onChange: (loc: LocationContext) => void
  onClose: () => void
}

type RecentLocation = LocationContext & { saved_at: number }

const RECENT_KEY = 'fitigo.recentLocations'

function loadRecent(): RecentLocation[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as RecentLocation[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveRecent(items: RecentLocation[]) {
  localStorage.setItem(RECENT_KEY, JSON.stringify(items.slice(0, 8)))
}

function toRecent(loc: LocationContext): RecentLocation {
  return { ...loc, saved_at: Date.now() }
}

const SUGGESTIONS: LocationContext[] = [
  {
    location_name: 'Kukatpally',
    latitude: 17.4948,
    longitude: 78.3996,
    city: 'Hyderabad',
    state: 'Telangana',
    country: 'India'
  },
  {
    location_name: 'Madhapur',
    latitude: 17.4483,
    longitude: 78.3915,
    city: 'Hyderabad',
    state: 'Telangana',
    country: 'India'
  },
  {
    location_name: 'Gachibowli',
    latitude: 17.4401,
    longitude: 78.3489,
    city: 'Hyderabad',
    state: 'Telangana',
    country: 'India'
  }
]

export default function LocationPickerModal({ open, value, onChange, onClose }: Props) {
  const modalRef = useRef<HTMLDivElement | null>(null)
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search, 250)
  const [loadingGps, setLoadingGps] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [recent, setRecent] = useState<RecentLocation[]>(() => loadRecent())

  const [remote, setRemote] = useState<LocationContext[]>([])
  const [loadingRemote, setLoadingRemote] = useState(false)

  useEffect(() => {
    if (!open) return
    setSearch('')
    setErr(null)
  }, [open])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    const q = debouncedSearch.trim()
    const url = q ? `/api/v1/meta/locations?search=${encodeURIComponent(q)}&limit=40` : `/api/v1/meta/locations?limit=40`

    setLoadingRemote(true)
    fetch(url)
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => {
        if (cancelled) return
        if (!Array.isArray(data)) {
          setRemote([])
          return
        }
        // Backend returns { location_name, latitude, longitude, city?, state?, country? }
        const mapped: LocationContext[] = data
          .map((it: any) => {
            if (!it?.location_name) return null
            const lat = Number(it.latitude)
            const lon = Number(it.longitude)
            if (Number.isNaN(lat) || Number.isNaN(lon)) return null
            return {
              location_name: String(it.location_name),
              latitude: lat,
              longitude: lon,
              city: it.city ?? undefined,
              state: it.state ?? undefined,
              country: it.country ?? undefined
            } satisfies LocationContext
          })
          .filter(Boolean) as LocationContext[]
        setRemote(mapped)
      })
      .catch(() => {
        if (cancelled) return
        setRemote([])
      })
      .finally(() => {
        if (cancelled) return
        setLoadingRemote(false)
      })

    return () => {
      cancelled = true
    }
  }, [open, debouncedSearch])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  const items = useMemo(() => {
    const q = search.trim().toLowerCase()

    // Merge backend-provided locations with a small static fallback.
    const merged = [...remote, ...SUGGESTIONS]
    const dedup = new Map<string, LocationContext>()
    for (const loc of merged) {
      const key = `${loc.location_name}-${loc.latitude}-${loc.longitude}`
      if (!dedup.has(key)) dedup.set(key, loc)
    }
    const base = Array.from(dedup.values())

    // Only show recent if no search
    if (!q && recent.length) {
      const rec = recent
        .slice()
        .sort((a, b) => b.saved_at - a.saved_at)
        .map(({ saved_at: _savedAt, ...loc }) => loc)
      return [{ header: 'Recent', list: rec }, { header: 'Suggested', list: base }]
    }

    const filtered = q
      ? base.filter((l) => {
          const hay = `${l.location_name} ${l.city ?? ''} ${l.state ?? ''}`.toLowerCase()
          return hay.includes(q)
        })
      : base

    const header = loadingRemote ? 'Searching…' : 'Locations'
    return [{ header, list: filtered }]
  }, [loadingRemote, remote, search, recent])

  if (!open) return null

  return (
    <div className={styles.lpOverlay} role="presentation" onMouseDown={onClose}>
      <div
        className={styles.lpModal}
        role="dialog"
        aria-modal="true"
        aria-label="Select location"
        ref={modalRef}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className={styles.lpHeader}>
          <div style={{ fontWeight: 700, fontSize: 16 }}>Choose your location</div>
          <button type="button" className={styles.iconBtn} onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className={styles.lpBody}>
          <div className={styles.lpSearchRow}>
            <span className={styles.searchIcon} aria-hidden="true">
              ⌕
            </span>
            <input
              className={styles.lpSearch}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search locality or city"
              aria-label="Search location"
              autoFocus
            />
            {search ? (
              <button
                type="button"
                className={styles.clearBtn}
                onClick={() => setSearch('')}
                aria-label="Clear search"
              >
                ×
              </button>
            ) : null}
          </div>

          {loadingRemote ? (
            <div style={{ marginTop: 10, color: '#64748b', fontSize: 12 }}>Loading locations…</div>
          ) : null}

          <button
            type="button"
            className={styles.lpGpsBtn}
            disabled={loadingGps}
            onClick={() => {
              setErr(null)
              if (!navigator.geolocation) {
                setErr('GPS location is not supported in this browser.')
                return
              }
              setLoadingGps(true)
              navigator.geolocation.getCurrentPosition(
                (pos) => {
                  const loc: LocationContext = {
                    location_name: 'Current Location',
                    latitude: pos.coords.latitude,
                    longitude: pos.coords.longitude
                  }
                  onChange(loc)
                  const next = [toRecent(loc), ...recent.filter((r) => r.location_name !== loc.location_name)]
                  setRecent(next)
                  saveRecent(next)
                  setLoadingGps(false)
                  onClose()
                },
                () => {
                  setLoadingGps(false)
                  setErr('We could not access your GPS location. Please select a locality instead.')
                },
                { enableHighAccuracy: false, timeout: 8000 }
              )
            }}
          >
            <span aria-hidden="true">📍</span>
            <span style={{ fontWeight: 650 }}>{loadingGps ? 'Detecting location…' : 'Use current GPS location'}</span>
          </button>

          {err ? <div className={styles.inlineError}>{err}</div> : null}

          <div className={styles.lpList}>
            {items.map((group) => (
              <div key={group.header} className={styles.lpGroup}>
                <div className={styles.lpGroupTitle}>{group.header}</div>
                <div className={styles.lpGroupList}>
                  {group.list.length ? (
                    group.list.map((loc) => {
                      const active =
                        loc.location_name === value.location_name &&
                        loc.latitude === value.latitude &&
                        loc.longitude === value.longitude
                      return (
                        <button
                          key={`${loc.location_name}-${loc.latitude}`}
                          type="button"
                          className={styles.lpItem}
                          onClick={() => {
                            onChange(loc)
                            const next = [toRecent(loc), ...recent.filter((r) => r.location_name !== loc.location_name)]
                            setRecent(next)
                            saveRecent(next)
                            onClose()
                          }}
                        >
                          <span className={styles.lpPin} aria-hidden="true">
                            ⦿
                          </span>
                          <span className={styles.lpItemText}>
                            <span style={{ fontWeight: 650 }}>{loc.location_name}</span>
                            <span className={styles.lpSub}>{[loc.city, loc.state].filter(Boolean).join(', ')}</span>
                          </span>
                          {active ? <span className={styles.lpActive}>Selected</span> : null}
                        </button>
                      )
                    })
                  ) : (
                    <div className={styles.lpEmpty}>No locations found.</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
