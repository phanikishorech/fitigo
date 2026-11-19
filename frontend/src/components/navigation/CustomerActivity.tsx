import { useEffect, useState } from 'react'
import { useSession } from '../../session/SessionGuard'
import { request } from '../../services/client'
import { subscribeActivity, type Activity } from '../../services/customerActivity'
import { Link } from '../common/UI'
import Icon from '../common/Icon'
import './customerActivity.css'

export default function CustomerActivity() {
  const session = useSession()
  const userId = session.status === 'authenticated' ? session.identity.user.id : null
  const [counts, setCounts] = useState<{ userId: number | null; cart: number; notifications: number }>({ userId: null, cart: 0, notifications: 0 })
  useEffect(() => {
    setCounts({ userId, cart: 0, notifications: 0 })
    if (userId === null) return
    let alive = true
    const running = new Set<Activity>(), queued = new Set<Activity>()
    async function refresh(kind: Activity) {
      if (!alive) return
      if (running.has(kind)) { queued.add(kind); return }
      running.add(kind)
      try {
        const result = kind === 'cart'
          ? await request<{ count: number }>('/cart/summary', { cache: 'no-store' }).then(data => data.count)
          : await request<{ enabled: boolean; unread_count: number }>('/notifications/inbox?limit=1&offset=0', { cache: 'no-store' }).then(data => data.enabled ? data.unread_count : 0)
        if (alive) setCounts(previous => ({ ...previous, userId, [kind]: Number.isSafeInteger(result) && result > 0 ? result : 0 }))
      } catch { if (alive) setCounts(previous => ({ ...previous, [kind]: 0 })) }
      finally { running.delete(kind); if (queued.delete(kind) && alive) void refresh(kind) }
    }
    const refreshAll = () => { if (document.visibilityState === 'hidden') return; void refresh('cart'); void refresh('notifications') }
    refreshAll()
    const off = subscribeActivity(kind => { void refresh(kind) })
    const timer = window.setInterval(refreshAll, 60000)
    window.addEventListener('focus', refreshAll); document.addEventListener('visibilitychange', refreshAll)
    return () => { alive = false; off(); clearInterval(timer); window.removeEventListener('focus', refreshAll); document.removeEventListener('visibilitychange', refreshAll) }
  }, [userId])
  const cart = counts.userId === userId && userId !== null ? counts.cart : 0
  const unread = counts.userId === userId && userId !== null ? counts.notifications : 0
  return <><Link to="/notifications" className="fg-icon-button fg-counted-icon" label={unread ? `Notifications, ${unread} unread` : 'Notifications'}><Icon name="bell" />{unread > 0 && <span className="fg-icon-count" aria-hidden="true">{unread > 99 ? '99+' : unread}</span>}</Link><Link to="/cart" className="fg-icon-button fg-counted-icon" label={cart ? `Your cart, ${cart} visit ${cart === 1 ? 'draft' : 'drafts'}` : 'Your cart'}><Icon name="bag" />{cart > 0 && <span className="fg-icon-count" aria-hidden="true">{cart > 99 ? '99+' : cart}</span>}</Link></>
}