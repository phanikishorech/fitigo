import { useCallback, useEffect, useRef, useState } from 'react'
import { accessService, type AccessCalendar, type TodayAccess } from '../services/accountService'
import { gymService } from '../services/gymService'
import type { GymDetailsResponse } from '../screens/GymDetails/types'
import { ApiError } from '../services/client'
import { membershipError } from './useMembershipResource'
import { hasAvailableAccess, todayFrom, utcTimestamp } from '../utils/membership'
import { visitAccessDecision } from '../services/visitAccessService'

type QrState = { loading: boolean; gym: GymDetailsResponse | null; calendar: AccessCalendar | null; access: TodayAccess | null; error: string; code?: string; checkedIn: boolean; needsRefresh: boolean }
export function useAccessQr(gymId: number) {
  const [state, setState] = useState<QrState>({ loading: true, gym: null, calendar: null, access: null, error: '', checkedIn: false, needsRefresh: false })
  const stateRef = useRef(state); stateRef.current = state
  const mounted = useRef(false); const lock = useRef(false); const generation = useRef(0); const shownQr = useRef(false)
  const [clock, setClock] = useState(Date.now())
  const load = useCallback(async () => {
    if (lock.current) return
    lock.current = true
    const version = ++generation.current
    const active = () => mounted.current && version === generation.current
    setState(previous => ({ ...previous, loading: true, error: '', code: undefined, access: null, needsRefresh: false }))
    try {
      const [gym, calendar] = await Promise.all([gymService.accessDetails(gymId), accessService.current()])
      if (!active()) return
      if (gym.membership_access.status !== 'INCLUDED') throw new ApiError('This gym is not available with your membership.', 403, 'GYM_NOT_ELIGIBLE')
      setState(previous => ({ ...previous, gym, calendar }))
      if (!hasAvailableAccess(calendar)) {
        const day = todayFrom(calendar)
        setState(previous => ({ ...previous, loading: false, checkedIn: day?.qr_status === 'USED' && !!day.checkin_time && shownQr.current }))
        return
      }
      if (visitAccessDecision(gym, calendar) !== 'MEMBERSHIP') throw new ApiError('This gym is not available with your membership.', 403, 'GYM_NOT_ELIGIBLE')
      // This existing endpoint mints the credential. Never manufacture a token in the browser.
      const access = await accessService.today()
      if (!active()) return
      // A server-issued single-gym credential must never be labelled as another gym's QR.
      if (access.status === 'ACTIVE' && access.access_type === 'SINGLE_GYM' && access.gym?.id !== gymId) throw new ApiError('This gym is not available with your membership.', 403, 'GYM_NOT_ELIGIBLE')
      const checkedIn = access.status === 'USED' && shownQr.current
      if (access.status === 'ACTIVE') shownQr.current = true
      setState(previous => ({ ...previous, access, loading: false, checkedIn }))
    } catch (error) {
      if (active()) setState(previous => ({ ...previous, loading: false, access: null, error: membershipError(error), code: error instanceof ApiError ? error.code : undefined }))
    } finally { if (version === generation.current) lock.current = false }
  }, [gymId])
  useEffect(() => {
    mounted.current = true
    void load()
    return () => { mounted.current = false; generation.current++; lock.current = false }
  }, [load])
  useEffect(() => {
    let polling = false; let disposed = false
    async function poll() {
      const current = stateRef.current
      if (polling || document.hidden || current.access?.status !== 'ACTIVE' || current.needsRefresh || current.loading) return
      polling = true
      const version = generation.current
      try {
        const calendar = await accessService.current()
        if (disposed || version !== generation.current || document.hidden) return
        const day = todayFrom(calendar)
        if (day?.qr_status === 'USED') {
          // The calendar response itself is authoritative proof of use. No scan is simulated.
          setState(previous => ({ ...previous, calendar, access: null, checkedIn: shownQr.current && !!day.checkin_time }))
        } else if (!hasAvailableAccess(calendar)) setState(previous => ({ ...previous, calendar, access: null }))
        else setState(previous => ({ ...previous, calendar }))
      } catch (error) {
        if (!disposed && version === generation.current) setState(previous => ({ ...previous, access: null, error: membershipError(error), needsRefresh: true }))
      } finally { polling = false }
    }
    const interval = window.setInterval(() => void poll(), 15000)
    const offline = () => {
      generation.current++; lock.current = false
      setState(previous => ({ ...previous, access: null, loading: false, needsRefresh: true, error: 'Unable to connect. Check your internet connection and try again.' }))
    }
    const hide = () => {
      if (document.hidden) {
        generation.current++; lock.current = false
        setState(previous => ({ ...previous, access: null, loading: false, needsRefresh: true }))
      }
    }
    document.addEventListener('visibilitychange', hide)
    window.addEventListener('offline', offline)
    return () => { disposed = true; clearInterval(interval); document.removeEventListener('visibilitychange', hide); window.removeEventListener('offline', offline) }
  }, [gymId])
  useEffect(() => {
    const timer = setInterval(() => {
      setClock(Date.now())
      const access = stateRef.current.access
      if (access?.status === 'ACTIVE' && Date.parse(utcTimestamp(access.expires_at)) <= Date.now()) {
        // Hide a token at its server-provided expiry; only a new backend request can renew it.
        setState(previous => ({ ...previous, access: null, needsRefresh: true }))
      }
    }, 1000)
    return () => clearInterval(timer)
  }, [])
  return { ...state, clock, refresh: load }
}