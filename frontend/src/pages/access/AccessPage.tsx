import { useEffect, useRef, useState } from 'react'
import AccessQr from '../../components/AccessQr'
import { useResource } from '../../hooks/useResource'
import { accessService, type AccessDay, type TodayAccess } from '../../services/accountService'
import { dateLabel } from '../../services/client'
import { Alert, Badge, Button, EmptyState, ErrorState, Heading, Link, Skeleton } from '../../components/common/UI'
import Icon from '../../components/common/Icon'

function TodayCard() {
  const [access, setAccess] = useState<TodayAccess | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(true)
  const [clock, setClock] = useState(Date.now())
  const [version, setVersion] = useState(0)
  const used = useRef<TodayAccess | null>(null)
  const utcDay = useRef(new Date().toISOString().slice(0, 10))
  useEffect(() => {
    let active = true, running = false
    async function load() {
      if (running || used.current?.status === 'USED') return
      running = true
      try {
        const data = await accessService.today()
        if (!active) return
        if (data.status === 'USED') used.current = data
        setAccess(data); setError('')
      } catch (e) { if (active) { setAccess(null); setError(e instanceof Error ? e.message : 'Unable to load access.') } }
      finally { running = false; if (active) setBusy(false) }
    }
    setBusy(true); void load()
    const poll = window.setInterval(() => { if (!document.hidden) void load() }, 15000)
    const focus = () => { if (used.current?.status !== 'USED') { setAccess(null); setBusy(true); void load() } }
    const visibility = () => { if (!document.hidden) focus(); else setAccess(null) }
    window.addEventListener('focus', focus); document.addEventListener('visibilitychange', visibility)
    return () => { active = false; clearInterval(poll); window.removeEventListener('focus', focus); document.removeEventListener('visibilitychange', visibility) }
  }, [version])
  useEffect(() => {
    const timer = setInterval(() => {
      setClock(Date.now())
      const day = new Date().toISOString().slice(0, 10)
      if (day !== utcDay.current) { utcDay.current = day; used.current = null; setAccess(null); setVersion(v => v + 1) }
      else if (used.current?.status === 'USED') setAccess(used.current)
    }, 1000)
    return () => clearInterval(timer)
  }, [])
  const refresh = () => { setAccess(null); setVersion(v => v + 1) }
  const valid = access?.status === 'ACTIVE' && Date.parse(access.expires_at) > clock
  return <section className="fg-panel fg-stack fg-center"><h2>Today’s gym access</h2><p className="fg-muted">{new Date().toLocaleDateString('en-IN', { timeZone: 'UTC', weekday: 'long', day: 'numeric', month: 'long' })} · UTC</p>{busy && !access ? <Skeleton cards={1} /> : error ? <><Alert>{error}</Alert><Button variant="secondary" onClick={refresh}>Try again</Button></> : access?.status === 'ACTIVE' && valid ? <><div><Badge tone="success">● Active · Valid today</Badge></div><h3>{access.gym?.name ?? 'Multi-gym membership'}</h3><div className="fg-qr-wrap"><AccessQr token={access.qr_token} /></div><p>Show this QR to gym staff.</p><small className="fg-muted">Expires in {Math.max(0, Math.ceil((Date.parse(access.expires_at) - clock) / 1000))} seconds · Refreshes automatically</small><p className="fg-muted">One check-in per day. Your QR is personal—do not share it.</p></> : access?.status === 'USED' ? <><div className="fg-success-mark"><Icon name="check" size={32} /></div><h3>Access already used</h3><p>This access has already been used today.</p><strong>{access.gym_name}</strong><p className="fg-muted">Checked in at {new Date(access.used_at).toLocaleString()}</p><Link to="/profile/history" className="fg-button fg-button--secondary">View check-in history</Link></> : access?.status === 'EXPIRED' || access?.status === 'ACTIVE' ? <><h3>QR expired</h3><p className="fg-muted">Your access QR is no longer valid. Refresh to check whether access is still available.</p><Button loading={busy} onClick={refresh}>Refresh access</Button><Link to="/profile/membership" className="fg-inline-link">View membership</Link></> : <><EmptyState title="No active access" description={access?.status === 'PAUSED' ? 'Your access is paused. Check your membership for details.' : 'You don’t have valid membership access today.'} /><Link to="/profile/membership" className="fg-button fg-button--primary">View membership</Link><Link to="/explore" className="fg-inline-link">Explore memberships</Link></>}</section>
}
export default function AccessPage({ calendar = false }: { calendar?: boolean }) {
  return <><Heading eyebrow="LESS WAITING. MORE MOVING." title={calendar ? 'Your access calendar' : 'Your workout starts here'} subtitle="Your membership access, ready at the entrance." />{calendar ? <div className="fg-two-column"><CalendarPanel /><TodayCard /></div> : <div className="fg-narrow"><TodayCard /><Link to="/profile/access" className="fg-inline-link">View access calendar <Icon name="calendar" size={18} /></Link></div>}</>
}
function CalendarPanel() {
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7))
  const [selected, setSelected] = useState<AccessDay | null>(null)
  const [year, monthNumber] = month.split('-').map(Number)
  const result = useResource(() => accessService.calendar(year, monthNumber), month)
  const move = (offset: number) => { setSelected(null); setMonth(new Date(Date.UTC(year, monthNumber - 1 + offset, 1)).toISOString().slice(0, 7)) }
  return <section className="fg-panel fg-stack"><div className="fg-row"><Button variant="text" aria-label="Previous month" disabled={month === '2000-01'} onClick={() => move(-1)}><Icon name="back" /></Button><h3>{new Date(Date.UTC(year, monthNumber - 1, 1)).toLocaleDateString('en-IN', { month: 'long', year: 'numeric', timeZone: 'UTC' })}</h3><Button variant="text" aria-label="Next month" disabled={month === '2100-12'} onClick={() => move(1)}><Icon name="arrow" /></Button></div>{result.loading ? <Skeleton cards={1} /> : result.error ? <ErrorState message={result.error} retry={result.retry} /> : <><p className="fg-muted">{result.data?.gym?.name ?? 'Membership access'} · Dates use UTC</p><div className="fg-calendar">{['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((label, i) => <span className="fg-calendar-label" key={i}>{label}</span>)}{Array.from({ length: new Date(Date.UTC(year, monthNumber - 1, 1)).getUTCDay() }, (_, i) => <span key={`space-${i}`} />)}{result.data?.days.map(day => <button key={day.date} className={day.qr_status === 'USED' ? 'used' : ''} aria-pressed={selected?.date === day.date} aria-label={`${day.date}: ${day.qr_status ?? day.status}`} onClick={() => setSelected(day)}>{Number(day.date.slice(-2))}<small>{day.qr_status === 'USED' ? 'Used' : day.qr_status === 'PAUSED' ? 'Paused' : day.status.replaceAll('_', ' ').toLowerCase()}</small></button>)}</div>{selected && <div className="fg-success" role="status"><strong>{dateLabel(selected.date)}</strong><p>{selected.qr_status ?? selected.status}{selected.gym_name && ` · ${selected.gym_name}`}</p>{selected.checkin_time && <p>Checked in at {selected.checkin_time} UTC</p>}</div>}<small className="fg-muted">Only today’s active access can display a QR. Past and future dates cannot generate entry codes.</small></>}</section>
}