import { useEffect, useRef } from 'react'
import { consumeReturnIntent, currentLocation, getReturnIntent, locationUrl, subscribeReturnIntent, type ReturnIntent } from './returnIntent'
import { useSession } from './SessionGuard'

export function usePendingAction(action: string, handler: (intent: ReturnIntent) => void | Promise<unknown>, ready = true) {
  const session = useSession()
  const location = locationUrl(currentLocation())
  const callback = useRef(handler); callback.current = handler
  useEffect(() => {
    if (!ready || session.status !== 'authenticated') return
    const resume = () => {
      const intent = getReturnIntent()
      if (!intent || intent.action !== action || locationUrl(intent) !== locationUrl(currentLocation())) return
      const claimed = consumeReturnIntent(intent.id, session.identity)
      if (claimed) {
        // Existing handlers own success/error UI; don't retain/replay mutation data.
        void Promise.resolve().then(() => callback.current(claimed)).catch(() => {})
      }
    }
    const timer = setTimeout(resume, 0)
    const unsubscribe = subscribeReturnIntent(resume)
    return () => { clearTimeout(timer); unsubscribe() }
  }, [action, ready, session, location])
}