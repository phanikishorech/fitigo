import { useEffect, useMemo, useRef, useState } from 'react'
import styles from './home.module.css'
import { navigate, scrollToId } from '../../router'
import { getStoredLocation, setStoredLocation } from '../NearbyGyms/LocationStore'
import type { LocationContext } from '../NearbyGyms/types'
import LocationPickerModal from '../NearbyGyms/LocationPickerModal'

type Props = {
  user: { firstName: string; email: string } | null
  headerCtaText: string
  initials: string
  onOpenAuth: (intent: string) => void
  onLogout: () => void
}

const DEFAULT_LOCATION: LocationContext = {
  location_name: 'Kukatpally',
  latitude: 17.4948,
  longitude: 78.3996,
  city: 'Hyderabad',
  state: 'Telangana',
  country: 'India'
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!mq) return
    const onChange = () => setReduced(Boolean(mq.matches))
    onChange()
    mq.addEventListener?.('change', onChange)
    return () => mq.removeEventListener?.('change', onChange)
  }, [])
  return reduced
}

function RotatingText({ text }: { text: string }) {
  const reduced = usePrefersReducedMotion()
  const chars = useMemo(() => {
    // ensure we have enough characters for a full circle
    const base = `${text} • `
    const repeated = base.repeat(3)
    return repeated.split('')
  }, [text])

  return (
    <div className={styles.rotateWrap} aria-hidden="true">
      <div className={`${styles.rotateCircle} ${reduced ? styles.rotateCircleReduced : ''}`}>
        {chars.map((c, i) => (
          <span
            key={i}
            className={styles.rotateChar}
            style={{ transform: `rotate(${i * 7.2}deg) translate(0, -88px)` }}
          >
            {c}
          </span>
        ))}
      </div>
    </div>
  )
}

function ProfileMenu({ user, onOpenAuth, onLogout }: { user: Props['user']; onOpenAuth: Props['onOpenAuth']; onLogout: Props['onLogout'] }) {
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
    { label: 'My Membership', to: '/membership' },
    { label: 'My Gym Access', to: '/my-access' },
    { label: 'Saved Gyms', to: '/saved' },
    { label: 'Bookings', to: '/bookings' },
    { label: 'Profile', to: '/profile' },
    { label: 'Settings', to: '/settings' }
  ]

  return (
    <div className={styles.profileWrap} ref={wrapRef}>
      <button
        type="button"
        className={styles.profileBtn}
        onClick={() => {
          if (!user) {
            onOpenAuth('header_auth')
            return
          }
          setOpen((v) => !v)
        }}
        aria-label={user ? 'Open member menu' : 'Login / Sign Up'}
      >
        {user ? <span className={styles.profileAvatar} aria-hidden="true" /> : <span className={styles.profileIcon} aria-hidden="true" />}
        <span className={styles.profileText}>{user ? user.firstName : 'Login / Sign Up'}</span>
      </button>

      {open ? (
        <div className={styles.profileMenu} role="menu" aria-label="Profile menu">
          {items.map((it) => (
            <button
              key={it.label}
              type="button"
              className={styles.profileMenuItem}
              role="menuitem"
              onClick={() => {
                setOpen(false)
                navigate(it.to)
              }}
            >
              {it.label}
            </button>
          ))}
          <div className={styles.profileMenuSep} />
          <button
            type="button"
            className={styles.profileMenuItem}
            role="menuitem"
            onClick={() => {
              setOpen(false)
              onLogout()
            }}
          >
            Logout
          </button>
        </div>
      ) : null}
    </div>
  )
}

export default function HomePage({ user, headerCtaText: _headerCtaText, initials: _initials, onOpenAuth, onLogout }: Props) {
  const [location, setLocation] = useState<LocationContext>(() => getStoredLocation() ?? DEFAULT_LOCATION)
  const [locationOpen, setLocationOpen] = useState(false)

  // Keep the stored location in sync so NearbyGyms opens with the same choice.
  useEffect(() => {
    setStoredLocation(location)
  }, [location])

  const [appLinks, setAppLinks] = useState<{ android: string | null; ios: string | null } | null>(null)

  useEffect(() => {
    // Load app links for QR/download card (backend-driven).
    fetch('/api/v1/meta/app-links')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d && (typeof d.android !== 'undefined' || typeof d.ios !== 'undefined')) setAppLinks(d)
      })
      .catch(() => {
        // Keep silent; card will show a subtle placeholder.
      })
  }, [])

  const gotoNearbyWithStoredLocation = () => {
    // Used by the collage floating action and tiles.
    // If user already selected a location pill, use it.
    // Otherwise, prompt the location picker.
    if (location?.latitude && location?.longitude) {
      navigate('/nearby')
      return
    }
    setLocationOpen(true)
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
            <span className={styles.logoWord}>FitiGo</span>
          </a>
        </div>

        <div className={styles.navCenter}>
          <button
            type="button"
            className={styles.navExplore}
            onClick={() => scrollToId('gym-discovery')}
            aria-label="Explore gyms"
          >
            <span className={styles.navExploreIcon} aria-hidden="true">
              ⊙
            </span>
            <span>Explore Gyms</span>
          </button>
        </div>

        <div className={styles.navRight}>
          <ProfileMenu user={user} onOpenAuth={onOpenAuth} onLogout={onLogout} />
        </div>
      </header>

      <main className={styles.heroWrap}>
        <div className={styles.heroInner}>
          <div className={styles.heroLeft}>
            <button type="button" className={styles.locationPill} onClick={() => setLocationOpen(true)}>
              <span className={styles.locationPin} aria-hidden="true">
                ⦿
              </span>
              <span className={styles.locationText}>{location.location_name}</span>
              <span className={styles.locationChevron} aria-hidden="true">
                ▾
              </span>
            </button>

            <h1 className={styles.heroH1}>
              <span>ONE MEMBERSHIP.</span>
              <span>ACCESS MULTIPLE GYMS.</span>
              <span>WORK OUT WHEREVER YOU WANT.</span>
            </h1>

            <p className={styles.heroDesc}>
              Discover gyms near you, choose the membership that fits your lifestyle, and work out at multiple fitness
              centers with one simple membership.
            </p>

            <div className={styles.heroCtas}>
              <button
                type="button"
                className={styles.primaryBtn}
                onClick={gotoNearbyWithStoredLocation}
              >
                Explore Nearby Gyms
              </button>

              <button type="button" className={styles.secondaryBtn} onClick={() => navigate('/membership')}>
                View Membership Plans
              </button>
            </div>
          </div>

          <RotatingText text="GYMS • FITNESS • WELLNESS • TRAIN • MOVE • REPEAT" />

          <div className={styles.heroRight}>
            <div className={styles.collage} aria-label="Featured fitness collage">
              <button
                type="button"
                className={`${styles.imgTile} ${styles.imgMain}`}
                onClick={gotoNearbyWithStoredLocation}
                aria-label="Explore general fitness gyms"
              >
                <img src="/hero/strength.svg" alt="Strength training" />
              </button>

              <button
                type="button"
                className={`${styles.imgTile} ${styles.imgTop}`}
                onClick={gotoNearbyWithStoredLocation}
                aria-label="Explore premium gyms"
              >
                <img src="/hero/gym-floor.svg" alt="Gym floor" />
              </button>

              <button
                type="button"
                className={`${styles.imgTile} ${styles.imgBottom}`}
                onClick={gotoNearbyWithStoredLocation}
                aria-label="Explore yoga & studio gyms"
              >
                <img src="/hero/studio.svg" alt="Studio workout" />
              </button>

              <button
                type="button"
                className={styles.floatingAction}
                onClick={gotoNearbyWithStoredLocation}
                aria-label="Quick explore nearby gyms"
              >
                ⊕
              </button>

              <div className={styles.downloadCard} role="group" aria-label="Download the app">
                <div className={styles.qrBox} aria-hidden="true">
                  <div className={styles.qrGrid} />
                </div>
                <div className={styles.dlText}>
                  <div className={styles.dlTitle}>DOWNLOAD</div>
                  <div className={styles.dlTitle}>THE APP</div>
                  <div className={styles.dlSub}>Find gyms and manage your membership on the go.</div>
                  <a
                    className={styles.dlLink}
                    href={appLinks?.android ?? appLinks?.ios ?? '#'}
                    onClick={(e) => {
                      const url = appLinks?.android ?? appLinks?.ios
                      if (!url) e.preventDefault()
                    }}
                    aria-disabled={!(appLinks?.android || appLinks?.ios)}
                  >
                    {appLinks?.android || appLinks?.ios ? 'Open store link' : 'Set ANDROID_APP_URL / IOS_APP_URL'}
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>

        <section className={styles.nextSection} id="gym-discovery">
          <div className={styles.nextInner}>
            <h2 className={styles.nextTitle}>Find the Perfect Gym for You</h2>
            <p className={styles.nextDesc}>
              Start by exploring partner gyms near your selected location. Filter by gym type, facilities, rating, and
              distance.
            </p>

            <div className={styles.nextActions}>
              <button type="button" className={styles.primaryBtnSmall} onClick={gotoNearbyWithStoredLocation}>
                Browse Nearby Gyms
              </button>
              <button type="button" className={styles.ghostBtnSmall} onClick={() => setLocationOpen(true)}>
                Change Location
              </button>
            </div>
          </div>
        </section>
      </main>

      <LocationPickerModal
        open={locationOpen}
        value={location}
        onChange={(loc) => setLocation(loc)}
        onClose={() => setLocationOpen(false)}
      />
    </div>
  )
}
