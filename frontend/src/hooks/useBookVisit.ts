import { useEffect, useRef, useState } from 'react'
import { getAccessToken, subscribeAuth } from '../auth'
import { openAuthModal } from '../authUi'
import { navigate } from '../router'
import { visitAccessService, visitDestination } from '../services/visitAccessService'

export function useBookVisit(gymId: number, resumeBook = false) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [choiceOpen, setChoiceOpen] = useState(false)
  const choiceLock = useRef(false)
  const lock = useRef(false)
  const generation = useRef(0)
  useEffect(() => () => { generation.current++ }, [gymId])
  useEffect(() => subscribeAuth(() => setChoiceOpen(false)), [])
  useEffect(() => {
    if (!resumeBook) return
    const timer = window.setTimeout(() => { void book() }, 0)
    return () => window.clearTimeout(timer)
  }, [gymId, resumeBook])
  async function book() {
    if (lock.current) return
    // Resume the decision after authentication, not a paid booking picked in advance.
    if (!getAccessToken()) { openAuthModal(`/gyms/${gymId}/visit?entry=book`); return }
    lock.current = true; setPending(true); setError('')
    const version = generation.current
    const token = getAccessToken()
    try {
      const result = await visitAccessService.check(gymId)
      if (version !== generation.current || token !== getAccessToken()) return
      if (result.decision === 'MEMBERSHIP') { choiceLock.current = false; setChoiceOpen(true) }
      else navigate(visitDestination(gymId, result.decision))
    } catch {
      if (version === generation.current) setError('Unable to check your membership access.')
    } finally {
      lock.current = false
      if (version === generation.current) setPending(false)
    }
  }
  function choose(others: boolean) {
    if (!choiceOpen || choiceLock.current) return
    choiceLock.current = true; setChoiceOpen(false)
    navigate(others ? `/gyms/${gymId}/book/schedule?for=others` : visitDestination(gymId, 'MEMBERSHIP'))
  }
  return { book, pending, error, choiceOpen, closeChoice: () => setChoiceOpen(false), useMembership: () => choose(false), bookForOthers: () => choose(true) }
}