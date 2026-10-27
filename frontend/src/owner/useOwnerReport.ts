import { useEffect, useRef } from 'react'
import { useResource } from '../hooks/useResource'

// Returning from the scanner/list remounts the dashboard. Visible polling also
// catches server webhooks and changes made by another staff member/device.
export function useOwnerReport<T>(loader: () => Promise<T>, key: string) {
  const resource = useResource(loader, key)
  const current = useRef(resource)
  current.current = resource
  useEffect(() => {
    let last = Date.now()
    const refresh = () => {
      if (document.visibilityState !== 'visible' || current.current.loading || Date.now() - last < 2000) return
      last = Date.now()
      current.current.retry()
    }
    const timer = window.setInterval(refresh, 30000)
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => { clearInterval(timer); window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh) }
  }, [key])
  return resource
}