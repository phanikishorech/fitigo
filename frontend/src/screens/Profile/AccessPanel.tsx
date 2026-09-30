import { useEffect, useRef, useState } from 'react'
import { authFetch } from '../../auth'
import AccessQr from '../../components/AccessQr'
import styles from './profile.module.css'

type Day = { date: string; status: string; qr_available: boolean; qr_status: string | null; gym_name: string | null; checkin_time: string | null }
type Calendar = { days: Day[]; access_type: string | null; gym: { name: string } | null }
type Today =
  | { status: 'ACTIVE'; qr_token: string; expires_at: string; access_type: string; gym: { name: string } | null }
  | { status: 'USED'; gym_name: string | null; used_at: string }
  | { status: 'PAUSED' | 'NO_ACCESS' | 'EXPIRED' }

export default function AccessPanel({ onCheckin }: { onCheckin: () => void }) {
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7))
  const [calendar, setCalendar] = useState<Calendar | null>(null)
  const [today, setToday] = useState<Today | null>(null)
  const [selected, setSelected] = useState<Day | null>(null)
  const [error, setError] = useState('')
  const [clock, setClock] = useState(Date.now())
  const [refresh, setRefresh] = useState(0)
  const [busy, setBusy] = useState(false)
  const lastUsed = useRef('')
  const onCheckinRef = useRef(onCheckin)
  onCheckinRef.current = onCheckin
  const [year, monthNumber] = month.split('-').map(Number)

  useEffect(() => {
    let cancelled = false
    let running = false
    setCalendar(null)
    setToday(null)
    setSelected(null)
    async function load() {
      if (running) return
      running = true
      setBusy(true)
      try {
        const responses = await Promise.all([
          authFetch(`/api/v1/customer/access-calendar?year=${year}&month=${monthNumber}`, { cache: 'no-store' }),
          authFetch('/api/v1/customer/access/today', { cache: 'no-store' })
        ])
        if (responses.some((r) => !r.ok)) throw new Error('Unable to load access. Please retry.')
        const [nextCalendar, nextToday] = await Promise.all(responses.map((r) => r.json())) as [Calendar, Today]
        if (cancelled) return
        // Both reads can straddle a scan; never leave today's cell actionable after USED.
        if (nextToday.status === 'USED') {
          nextCalendar.days = nextCalendar.days.map((day) => day.status === 'TODAY'
            ? { ...day, qr_available: false, qr_status: 'USED', gym_name: nextToday.gym_name, checkin_time: nextToday.used_at.slice(11, 19) }
            : day)
        }
        setCalendar(nextCalendar)
        setToday(nextToday)
        setSelected((previous) => nextCalendar.days.find((day) => day.date === previous?.date) ?? null)
        setClock(Date.now())
        setError('')
        if (nextToday.status === 'USED' && lastUsed.current !== nextToday.used_at) {
          lastUsed.current = nextToday.used_at
          onCheckinRef.current()
        }
      } catch (e) {
        if (!cancelled) { setToday(null); setError(e instanceof Error ? e.message : 'Unable to load access') }
      } finally {
        running = false
        if (!cancelled) setBusy(false)
      }
    }
    void load()
    const poll = window.setInterval(() => { if (!document.hidden) void load() }, 15000)
    const focus = () => { setToday(null); void load() }
    const visibility = () => { if (!document.hidden) focus() }
    window.addEventListener('focus', focus)
    document.addEventListener('visibilitychange', visibility)
    return () => {
      cancelled = true
      window.clearInterval(poll)
      window.removeEventListener('focus', focus)
      document.removeEventListener('visibilitychange', visibility)
    }
  }, [year, monthNumber, refresh])

  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const moveMonth = (offset: number) => {
    setMonth(new Date(Date.UTC(year, monthNumber - 1 + offset, 1)).toISOString().slice(0, 7))
  }
  const active = today?.status === 'ACTIVE' && Date.parse(today.expires_at) > clock
  return <section className={styles.calWrap} aria-label="Membership access calendar and QR">
    <div className={styles.calHeader}>
      <button type="button" className={styles.secondaryBtn} aria-label="Previous month" disabled={month === '2000-01'} onClick={() => moveMonth(-1)}>←</button>
      <strong>{new Date(Date.UTC(year, monthNumber - 1, 1)).toLocaleDateString(undefined, { month: 'long', year: 'numeric', timeZone: 'UTC' })}</strong>
      <button type="button" className={styles.secondaryBtn} aria-label="Next month" disabled={month === '2100-12'} onClick={() => moveMonth(1)}>→</button>
    </div>
    {error && <p role="alert">{error}</p>}
    {!calendar ? <p>{error ? 'Calendar unavailable.' : 'Loading calendar…'}</p> : <>
      <p>{calendar.gym?.name ?? (calendar.access_type === 'MULTI_GYM' ? 'Multi-gym access' : 'Access history')}</p>
      <div className={styles.calDowRow}>{['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day) => <div key={day}>{day}</div>)}</div>
      <div className={styles.calGrid}>
        {Array.from({ length: new Date(Date.UTC(year, monthNumber - 1, 1)).getUTCDay() }, (_, i) => <div key={`blank-${i}`} />)}
        {calendar.days.map((day) => {
          const label = day.qr_status === 'USED' ? 'Visited' : day.qr_status === 'PAUSED' ? 'Paused' : day.status.replaceAll('_', ' ').toLowerCase()
          return <button type="button" key={day.date}
            className={[styles.calCell, day.status === 'TODAY' ? styles.calCellToday : '', day.qr_status === 'USED' ? styles.calCellAccessed : '', day.qr_available ? styles.calCellActive : '', day.qr_status === 'PAUSED' ? styles.accessPaused : ''].join(' ')}
            aria-label={`${day.date}: ${label}${day.gym_name ? ` at ${day.gym_name}` : ''}`} aria-pressed={selected?.date === day.date}
            onClick={() => setSelected(day)}>
            <span>{Number(day.date.slice(-2))}</span><small className={styles.accessDayLabel}>{label}</small>
          </button>
        })}
      </div>
      {selected && <p role="status">{selected.date}: {selected.qr_status ?? selected.status}{selected.gym_name ? ` — ${selected.gym_name}` : ''}{selected.checkin_time ? ` at ${selected.checkin_time} UTC` : ''}</p>}
    </>}
    <div className={styles.accessPass}>
      <h3>Today's access</h3>
      {today?.status === 'ACTIVE' && active ? <>
        <p>{today.gym?.name ?? 'Multi-gym access'}</p>
        <AccessQr token={today.qr_token} />
        <p>Show this QR to gym staff. One check-in per day.</p>
        <small>Refreshes automatically · expires in {Math.max(0, Math.ceil((Date.parse(today.expires_at) - clock) / 1000))} seconds</small>
      </> : <p role="status">{today?.status === 'USED' ? `Access used at ${today.gym_name ?? 'the gym'} · ${new Date(today.used_at).toLocaleTimeString()}`
        : today?.status === 'PAUSED' ? 'This visit has been paused.'
          : today?.status === 'NO_ACCESS' ? 'No active gym access.'
            : today ? 'QR expired. Refresh to check availability.' : error ? 'QR unavailable.' : 'Loading today’s access…'}</p>}
      <button type="button" className={styles.secondaryBtn} disabled={busy} onClick={() => { setToday(null); setRefresh((n) => n + 1) }}>Refresh access</button>
      <p className={styles.mutedSmall}>Calendar dates and daily access use UTC. Past and future dates cannot issue a QR.</p>
    </div>
  </section>
}