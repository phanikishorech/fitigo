import { useEffect } from 'react'

// Refresh from the server on return and at its next price boundary. Never compute an offer locally.
export function usePlanRefresh(retry: () => void, validUntil?: string, serverTime?: string) {
  useEffect(() => {
    const refresh = () => { if (!document.hidden) retry() }
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    // Also pick up admin price changes and newly-started promotions while browsing.
    const interval = window.setInterval(refresh, 60000)
    let timer: number | undefined
    if (validUntil) {
      const remaining = Date.parse(validUntil) - (serverTime ? Date.parse(serverTime) : Date.now())
      if (Number.isFinite(remaining)) timer = window.setTimeout(refresh, Math.max(1000, Math.min(remaining + 250, 2147483647)))
    }
    return () => { window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh); window.clearTimeout(timer); window.clearInterval(interval) }
  }, [retry, validUntil, serverTime])
}