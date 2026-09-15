import { ReactNode, useEffect, useState } from 'react'
import styles from './admin.module.css'
import { navigate } from '../../router'
import { clearTokens, getAccessToken } from '../../auth'
import { authFetch } from '../../auth'

async function fetchMyRoles(): Promise<string[]> {
  const r = await authFetch('/api/v1/users/me/roles')
  const data = await r.json().catch(() => ([] as any))
  if (!r.ok) throw new Error((data as any)?.detail ?? 'Failed to load roles')
  return data as string[]
}

export default function AdminLayout({ title, children, active }: { title: string; children: ReactNode; active: 'dashboard' | 'users' | 'gyms' | 'bookings' }) {
  const [roles, setRoles] = useState<{ status: 'loading' } | { status: 'ready'; roles: string[] } | { status: 'error'; message: string }>({ status: 'loading' })

  useEffect(() => {
    const token = getAccessToken()
    if (!token) {
      navigate('/admin/login')
      return
    }

    fetchMyRoles()
      .then((r) => setRoles({ status: 'ready', roles: r }))
      .catch((e) => setRoles({ status: 'error', message: e?.message ?? 'Failed to load roles' }))
  }, [])

  const hasAdminRole = roles.status === 'ready' ? roles.roles.includes('ADMIN') || roles.roles.includes('SUPER_ADMIN') : false

  return (
    <div className={styles.pageRoot}>
      <header className={styles.navbar}>
        <div className={styles.navLeft}>
          <a className={styles.logo} href="/" onClick={(e) => { e.preventDefault(); navigate('/') }}>
            FitiGo
          </a>
          <span className={styles.subtle}>Admin Portal</span>
        </div>

        <div className={styles.navRight}>
          <button type="button" className={`${styles.navBtn} ${active === 'dashboard' ? styles.navBtnActive : ''}`} onClick={() => navigate('/admin')}>
            Dashboard
          </button>
          <button type="button" className={`${styles.navBtn} ${active === 'users' ? styles.navBtnActive : ''}`} onClick={() => navigate('/admin/users')}>
            Users
          </button>
          <button type="button" className={`${styles.navBtn} ${active === 'gyms' ? styles.navBtnActive : ''}`} onClick={() => navigate('/admin/gyms')}>
            Gyms
          </button>
          <button type="button" className={`${styles.navBtn} ${active === 'bookings' ? styles.navBtnActive : ''}`} onClick={() => navigate('/admin/bookings')}>
            Bookings
          </button>
          <button type="button" className={styles.navBtn} onClick={() => navigate('/profile')}>
            Profile
          </button>
          <button
            type="button"
            className={styles.navBtn}
            onClick={() => {
              clearTokens()
              navigate('/admin/login')
            }}
          >
            Logout
          </button>
        </div>
      </header>

      <main className={styles.content}>
        <div className={styles.topbar}>
          <div>
            <div className={styles.title}>{title}</div>
            <div className={styles.subtle}>Manage users, gym approvals, and bookings.</div>
          </div>
          <button type="button" className={styles.linkBtn} onClick={() => navigate('/')}
          >
            Back to consumer app
          </button>
        </div>

        {roles.status === 'loading' ? (
          <div className={styles.panel}>Loading…</div>
        ) : roles.status === 'error' ? (
          <div className={styles.panel}>Error: {roles.message}</div>
        ) : !hasAdminRole ? (
          <div className={styles.panel}>
            <div className={styles.panelTitle}>Access denied</div>
            <div className={styles.subtle}>Your account does not have Admin permissions.</div>
          </div>
        ) : (
          children
        )}
      </main>
    </div>
  )
}
