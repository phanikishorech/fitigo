import { useEffect, useMemo, useState } from 'react'
import styles from './gymAccess.module.css'
import {
  addClassToCart,
  addGymToCart,
  fetchBookingOptions,
  fetchCartItems,
  fetchClassSessions,
  fetchOperatingHoursForDate,
  removeCartItem
} from './api'
import type {
  CartItemResponse,
  ClassSessionPublicResponse,
  GymBookingOptionsResponse,
  OperatingHoursForDateResponse
} from './types'
import SupportWidget from '../NearbyGyms/SupportWidget'
import AppDownloadModal from '../NearbyGyms/AppDownloadModal'
import { navigate } from '../../router'
import ProfileIconButton from '../../components/ProfileIconButton'

function todayISO() {
  const d = new Date()
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

function fmtDate(iso: string) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' })
}

function bannerClass(tone: string) {
  if (tone === 'success') return styles.banner
  if (tone === 'warn') return `${styles.banner} ${styles.bannerWarn}`
  return `${styles.banner} ${styles.bannerInfo}`
}

function clampInt(n: number, min: number, max: number) {
  if (!Number.isFinite(n)) return min
  return Math.max(min, Math.min(max, Math.trunc(n)))
}

function toHHMM(v: string) {
  // input[type=time] can return HH:MM or HH:MM:SS depending on browser
  const parts = v.split(':')
  if (parts.length < 2) return v
  return `${parts[0].padStart(2, '0')}:${parts[1].padStart(2, '0')}`
}

function addMinutesToHHMM(v: string, minutesToAdd: number) {
  const mm = timeToMins(v)
  if (mm == null) return v
  const out = mm + minutesToAdd
  const hh = Math.floor((out % (24 * 60)) / 60)
  const mins = out % 60
  return `${String(hh).padStart(2, '0')}:${String(mins).padStart(2, '0')}`
}

function timeToMins(v: string | null | undefined) {
  if (!v) return null
  const parts = v.split(':')
  if (parts.length < 2) return null
  const hh = Number(parts[0])
  const mm = Number(parts[1])
  if (!Number.isFinite(hh) || !Number.isFinite(mm)) return null
  return hh * 60 + mm
}

export default function GymAccessPage({ gymId }: { gymId: number }) {
  const [appOpen, setAppOpen] = useState(false)
  const [options, setOptions] = useState<GymBookingOptionsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [bookingType, setBookingType] = useState<'GYM' | 'CLASS'>('GYM')
  const [visitDate, setVisitDate] = useState(todayISO())
  const [memberCount, setMemberCount] = useState(1)

  // gym booking fields
  const [preferredStartTime, setPreferredStartTime] = useState<string>('')
  const [preferredEndTime, setPreferredEndTime] = useState<string>('')
  const [operatingHours, setOperatingHours] = useState<OperatingHoursForDateResponse | null>(null)

  // class booking fields
  const [classSessions, setClassSessions] = useState<ClassSessionPublicResponse[]>([])
  const [classSessionsLoading, setClassSessionsLoading] = useState(false)
  const [selectedClassSessionId, setSelectedClassSessionId] = useState<number | ''>('')

  // cart
  const [cartItems, setCartItems] = useState<CartItemResponse[]>([])
  const [cartLoading, setCartLoading] = useState(false)
  const [addingToCart, setAddingToCart] = useState(false)

  const [createdInfo, setCreatedInfo] = useState<string | null>(null)

  const classesSelectable = Boolean(options?.has_classes && options?.classes_available)

  const selectedClassSession = useMemo(() => {
    if (selectedClassSessionId === '') return null
    return classSessions.find((s) => s.id === selectedClassSessionId) ?? null
  }, [classSessions, selectedClassSessionId])

  const gymPricePerPerson = useMemo(() => {
    const p = Number(options?.gym_price_per_person ?? 0)
    return Number.isFinite(p) ? p : 0
  }, [options?.gym_price_per_person])

  const bookingPricePerPerson = useMemo(() => {
    if (bookingType === 'GYM') return gymPricePerPerson
    const p = Number(selectedClassSession?.price_per_person ?? 0)
    return Number.isFinite(p) ? p : 0
  }, [bookingType, gymPricePerPerson, selectedClassSession?.price_per_person])

  const bookingTotal = useMemo(() => bookingPricePerPerson * memberCount, [bookingPricePerPerson, memberCount])

  const cartTotal = useMemo(() => {
    return cartItems.reduce((acc, it) => acc + (Number(it.total_price) || 0), 0)
  }, [cartItems])

  const reloadCart = async () => {
    setCartLoading(true)
    try {
      const d = await fetchCartItems()
      setCartItems(d)
    } catch {
      setCartItems([])
    } finally {
      setCartLoading(false)
    }
  }

  // Load booking options
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchBookingOptions(gymId)
      .then((d) => {
        if (cancelled) return
        setOptions(d)
      })
      .catch((e) => {
        if (cancelled) return
        setError(e?.message ?? 'Failed to load booking options')
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [gymId])

  // Load cart on gym change
  useEffect(() => {
    reloadCart()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gymId])

  // Load operating hours when date changes
  useEffect(() => {
    if (!visitDate) return
    fetchOperatingHoursForDate(gymId, visitDate)
      .then((d) => setOperatingHours(d))
      .catch(() => setOperatingHours(null))
  }, [gymId, visitDate])

  // Load class sessions for selected date
  useEffect(() => {
    if (bookingType !== 'CLASS') return
    if (!visitDate) return
    if (!classesSelectable) return
    setClassSessionsLoading(true)
    fetchClassSessions(gymId, visitDate)
      .then((d) => {
        setClassSessions(d)
        if (selectedClassSessionId !== '' && !d.some((s) => s.id === selectedClassSessionId)) setSelectedClassSessionId('')
      })
      .catch(() => setClassSessions([]))
      .finally(() => setClassSessionsLoading(false))
  }, [gymId, visitDate, bookingType, classesSelectable, selectedClassSessionId])

  // Keep bookingType valid
  useEffect(() => {
    if (!classesSelectable && bookingType === 'CLASS') {
      setBookingType('GYM')
      setSelectedClassSessionId('')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classesSelectable])

  // When switching booking types, clear invalid selections
  useEffect(() => {
    setCreatedInfo(null)
    if (bookingType === 'GYM') {
      setSelectedClassSessionId('')
    } else {
      setPreferredStartTime('')
      setPreferredEndTime('')
    }
  }, [bookingType])

  // Auto-compute end time for gym access (UI only asks for start time)
  useEffect(() => {
    if (bookingType !== 'GYM') return
    if (!preferredStartTime) {
      setPreferredEndTime('')
      return
    }
    // Default visit window = 30 minutes
    setPreferredEndTime(addMinutesToHHMM(toHHMM(preferredStartTime), 30))
  }, [bookingType, preferredStartTime])

  // Clamp members to capacity
  useEffect(() => {
    if (bookingType !== 'CLASS') return
    if (!selectedClassSession?.available_capacity) return
    setMemberCount((v) => clampInt(v, 1, selectedClassSession.available_capacity))
  }, [bookingType, selectedClassSession?.available_capacity])

  const addToCart = async () => {
    setCreatedInfo(null)
    if (addingToCart) return
    setAddingToCart(true)
    try {
      if (bookingType === 'GYM') {
        if (!visitDate) throw new Error('Please select a date')
        if (!preferredStartTime) throw new Error('Please select preferred visit time')
        if (operatingHours?.is_closed) throw new Error('Gym is closed on the selected date')

        const openM = timeToMins(operatingHours?.open_time ?? null)
        const closeM = timeToMins(operatingHours?.close_time ?? null)
        const startM = timeToMins(preferredStartTime)
        const endM = timeToMins(preferredEndTime)
        if (openM != null && startM != null && startM < openM) throw new Error('Start time must be within opening hours')
        if (closeM != null && endM != null && endM > closeM) throw new Error('Selected time must be within opening hours')
        if (startM != null && endM != null && endM <= startM) throw new Error('End time must be after start time')

        const res = await addGymToCart({
          booking_type: 'GYM',
          gym_id: gymId,
          booking_date: visitDate,
          preferred_start_time: toHHMM(preferredStartTime),
          preferred_end_time: toHHMM(preferredEndTime),
          member_count: memberCount
        })
        setCreatedInfo(`Added to cart (Item #${res.id})`)
        await reloadCart()
      } else {
        if (!visitDate) throw new Error('Please select a date')
        if (!selectedClassSession) throw new Error('Please select a class session')

        const cap = selectedClassSession.available_capacity
        if (cap != null && memberCount > cap) throw new Error(`Only ${cap} slots are available for this class.`)

        const res = await addClassToCart({
          booking_type: 'CLASS',
          gym_id: gymId,
          booking_date: visitDate,
          class_session_id: selectedClassSession.id,
          member_count: memberCount
        })
        setCreatedInfo(`Added to cart (Item #${res.id})`)
        await reloadCart()
      }
    } catch (e: any) {
      setCreatedInfo(e?.message ?? 'Unable to add to cart')
    } finally {
      setAddingToCart(false)
    }
  }

  const onProceed = () => {
    if (cartItems.length === 0) return
    navigate('/checkout')
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
            className={`${styles.navItem} ${styles.navItemActive}`}
            href="/nearby"
            onClick={(e) => {
              e.preventDefault()
              navigate('/nearby')
            }}
          >
            EXPLORE
          </a>
          <a className={styles.navItem} href="/membership" onClick={(e) => { e.preventDefault(); navigate('/membership') }}>
            MEMBERSHIP
          </a>
          <a
            className={styles.navItem}
            href="/classes"
            onClick={(e) => { e.preventDefault(); navigate('/classes') }}
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
          {loading ? (
            <div className={styles.grid}>
              <div className={styles.card}>
                <div className={styles.skeleton} style={{ height: 18, width: 320, borderRadius: 10 }} />
                <div className={styles.skeleton} style={{ height: 14, width: 220, borderRadius: 10, marginTop: 10 }} />
                <div className={styles.skeleton} style={{ height: 44, width: '100%', borderRadius: 12, marginTop: 14 }} />
                <div className={styles.skeleton} style={{ height: 220, width: '100%', borderRadius: 14, marginTop: 14 }} />
              </div>
              <div className={styles.card}>
                <div className={styles.skeleton} style={{ height: 280, width: '100%' }} />
              </div>
            </div>
          ) : error || !options ? (
            <div className={styles.card}>
              <div className={styles.title}>Unable to load booking</div>
              <div className={styles.subtitle}>{error ?? 'Please try again.'}</div>
              <div style={{ marginTop: 14, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <button className={styles.getAppBtn} type="button" onClick={() => window.location.reload()}>
                  Try Again
                </button>
                <button className={styles.profileBtn} type="button" onClick={() => navigate('/nearby')}>
                  ←
                </button>
              </div>
            </div>
          ) : (
            <div className={styles.grid}>
              <section className={styles.card} aria-label="Gym access form">
                <div>
                  <h1 className={styles.title}>
                    {options.gym_name} {options.locality ? `- ${options.locality}` : ''}
                  </h1>
                  <div className={styles.subtitle}>{[options.locality, options.city].filter(Boolean).join(', ') || 'Location'}</div>

                  <div className={bannerClass(options.membership_status.tone)}>
                    <div className={styles.bannerTitle}>{options.membership_status.title}</div>
                    {options.membership_status.subtitle ? <div className={styles.bannerSub}>{options.membership_status.subtitle}</div> : null}
                  </div>
                </div>

                <div className={styles.form}>
                  <div className={styles.row}>
                    <div className={styles.label}>WHAT WOULD YOU LIKE TO BOOK?</div>
                    <div style={{ display: 'grid', gap: 10 }}>
                      <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                        <input type="radio" name="bookingType" checked={bookingType === 'GYM'} onChange={() => setBookingType('GYM')} />
                        <div>
                          <div style={{ fontWeight: 900 }}>Gym</div>
                          <div className={styles.muted}>Access the gym during its operating hours.</div>
                        </div>
                      </label>

                      {options.has_classes ? (
                        <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', opacity: classesSelectable ? 1 : 0.55 }}>
                          <input
                            type="radio"
                            name="bookingType"
                            checked={bookingType === 'CLASS'}
                            onChange={() => setBookingType('CLASS')}
                            disabled={!classesSelectable}
                          />
                          <div>
                            <div style={{ fontWeight: 900 }}>Classes</div>
                            <div className={styles.muted}>Join a scheduled fitness class.</div>
                            {!classesSelectable ? (
                              <div className={styles.muted} style={{ marginTop: 4 }}>
                                {options.classes_unavailable_message ?? 'Classes are not available at this gym.'}
                              </div>
                            ) : null}
                          </div>
                        </label>
                      ) : null}
                    </div>
                  </div>

                  <div className={styles.row}>
                    <div className={styles.label}>Date</div>
                    <input className={styles.control} type="date" value={visitDate} onChange={(e) => setVisitDate(e.target.value)} />
                  </div>

                  <div className={styles.row}>
                    <div className={styles.label}>Members</div>
                    <div className={styles.durationWrap}>
                      <button type="button" className={styles.roundBtn} onClick={() => setMemberCount((v) => clampInt(v - 1, 1, 50))} disabled={memberCount <= 1}>
                        −
                      </button>
                      <div className={styles.durationText}>{memberCount}</div>
                      <button
                        type="button"
                        className={styles.roundBtn}
                        onClick={() => {
                          if (bookingType === 'CLASS' && selectedClassSession?.available_capacity != null) {
                            setMemberCount((v) => clampInt(v + 1, 1, selectedClassSession.available_capacity))
                            return
                          }
                          setMemberCount((v) => clampInt(v + 1, 1, 50))
                        }}
                        disabled={bookingType === 'CLASS' && selectedClassSession?.available_capacity != null ? memberCount >= selectedClassSession.available_capacity : false}
                      >
                        +
                      </button>
                    </div>
                  </div>

                  {bookingType === 'GYM' ? (
                    <>
                      <div className={styles.row}>
                        <div className={styles.label}>Opening Hours</div>
                        <div style={{ fontWeight: 850 }}>{operatingHours?.label ?? 'Hours not available'}</div>
                      </div>

                      <div className={styles.row}>
                        <div className={styles.label}>Preferred Visit Time</div>
                        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                          <input
                            className={styles.control}
                            type="time"
                            step={1800}
                            value={preferredStartTime}
                            onChange={(e) => setPreferredStartTime(e.target.value)}
                            disabled={Boolean(operatingHours?.is_closed)}
                          />
                          <div className={styles.muted} style={{ alignSelf: 'center' }}>
                            (30 min slots)
                          </div>
                        </div>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className={styles.row}>
                        <div className={styles.label}>Available Classes</div>
                        <select
                          className={styles.control}
                          value={selectedClassSessionId === '' ? '' : String(selectedClassSessionId)}
                          onChange={(e) => setSelectedClassSessionId(e.target.value ? Number(e.target.value) : '')}
                          disabled={!classesSelectable || classSessionsLoading}
                        >
                          <option value="">{classSessionsLoading ? 'Loading…' : '--Select a class session--'}</option>
                          {classSessions.map((s) => (
                            <option key={s.id} value={String(s.id)} disabled={s.status === 'FULL' || s.status === 'CANCELLED' || s.status === 'CLOSED'}>
                              {s.class_name} · {s.start_time} - {s.end_time} · ₹{Number(s.price_per_person).toFixed(0)} ·{' '}
                              {s.status === 'FULL' ? 'FULL' : `${s.available_capacity} left`}
                            </option>
                          ))}
                        </select>
                      </div>

                      {selectedClassSession ? (
                        <div className={styles.row}>
                          <div className={styles.label}>Class Info</div>
                          <div className={styles.muted}>
                            Time: {selectedClassSession.start_time} - {selectedClassSession.end_time} · Available:{' '}
                            {selectedClassSession.available_capacity}
                          </div>
                        </div>
                      ) : null}
                    </>
                  )}

                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 8 }}>
                    <button className={styles.finalBtn} type="button" onClick={addToCart} disabled={addingToCart}>
                      Add to Cart
                    </button>
                  </div>
                </div>
              </section>

              <aside className={styles.card} aria-label="Booking summary">
                <div style={{ fontWeight: 950, marginBottom: 10 }}>BOOKING SUMMARY</div>
                <div className={styles.muted} style={{ marginBottom: 10 }}>
                  Booking Type: <span style={{ fontWeight: 850, color: '#0f172a' }}>{bookingType === 'GYM' ? 'Gym' : 'Classes'}</span>
                </div>
                {bookingType === 'GYM' ? (
                  <div style={{ display: 'grid', gap: 8 }}>
                    <div className={styles.muted}>Date: {fmtDate(visitDate)}</div>
                    <div className={styles.muted}>Opening Hours: {operatingHours?.label ?? '—'}</div>
                    <div className={styles.muted}>
                      Preferred Time: {preferredStartTime || '—'}
                    </div>
                  </div>
                ) : (
                  <div style={{ display: 'grid', gap: 8 }}>
                    <div className={styles.muted}>Date: {fmtDate(visitDate)}</div>
                    <div className={styles.muted}>Class: {selectedClassSession ? selectedClassSession.class_name : '—'}</div>
                    <div className={styles.muted}>
                      Time: {selectedClassSession ? `${selectedClassSession.start_time} - ${selectedClassSession.end_time}` : '—'}
                    </div>
                    <div className={styles.muted}>
                      Available Slots: {selectedClassSession ? String(selectedClassSession.available_capacity) : '—'}
                    </div>
                  </div>
                )}

                <div style={{ marginTop: 12, borderTop: '1px solid var(--line)' }} />

                <div style={{ marginTop: 12, display: 'grid', gap: 6 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                    <span className={styles.muted}>Price per person</span>
                    <span style={{ fontWeight: 900 }}>₹{bookingPricePerPerson.toFixed(0)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                    <span className={styles.muted}>Members</span>
                    <span style={{ fontWeight: 900 }}>{memberCount}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                    <span className={styles.muted}>Total</span>
                    <span style={{ fontWeight: 950 }}>₹{bookingTotal.toFixed(0)}</span>
                  </div>
                </div>

                {createdInfo ? <div className={styles.muted} style={{ marginTop: 12 }}>{createdInfo}</div> : null}

                <div style={{ marginTop: 18, borderTop: '1px solid var(--line)' }} />

                <div style={{ fontWeight: 950, marginTop: 14, marginBottom: 10 }}>YOUR CART</div>
                {cartLoading ? (
                  <div className={styles.muted}>Loading cart…</div>
                ) : cartItems.length === 0 ? (
                  <div className={styles.muted}>No items in cart.</div>
                ) : (
                  <div className={styles.summaryList}>
                    {cartItems.map((c) => (
                      <div key={c.id} className={styles.bookingCard}>
                        <div className={styles.bookingTop}>
                          <div>
                            <div style={{ fontWeight: 950 }}>{c.booking_type === 'CLASS' ? c.class_name ?? 'Class' : 'Gym Access'}</div>
                            <div className={styles.muted} style={{ marginTop: 6 }}>
                              {fmtDate(c.booking_date)} · Members: {c.member_count} · ₹{Number(c.total_price).toFixed(0)}
                            </div>
                          </div>
                          <button
                            type="button"
                            className={styles.linkBtn}
                            onClick={async () => {
                              try {
                                await removeCartItem(c.id)
                              } finally {
                                reloadCart()
                              }
                            }}
                            aria-label="Remove"
                          >
                            ✕
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <button
                  style={{ marginTop: 12 }}
                  className={styles.primaryBtn}
                  type="button"
                  onClick={onProceed}
                  disabled={cartLoading || cartItems.length === 0}
                >
                  Proceed ₹{cartTotal.toFixed(2)}
                </button>
              </aside>
            </div>
          )}
        </div>
      </main>

      <SupportWidget />
      <AppDownloadModal open={appOpen} onClose={() => setAppOpen(false)} />
    </div>
  )
}
