import { ReactNode, useEffect, useState } from 'react'
import styles from './gymOwner.module.css'
import { navigate } from '../../router'
import { clearTokens, getAccessToken } from '../../auth'
import { fetchMyRoles } from './api'

export default function OwnerLayout({ title, children, active }: { title: string; children: ReactNode; active: 'dashboard' | 'gyms' }) {
  const [roles, setRoles] = useState<{ status: 'loading' } | { status: 'ready'; roles: string[] } | { status: 'error'; message: string }>({
    status: 'loading'
  })

  useEffect(() => {
    const token = getAccessToken()
    if (!token) {
      navigate('/owner/login')
      return
    }

    fetchMyRoles()
      .then((r) => setRoles({ status: 'ready', roles: r }))
      .catch((e) => setRoles({ status: 'error', message: e?.message ?? 'Failed to load roles' }))
  }, [])

  const hasOwnerRole = roles.status === 'ready' ? roles.roles.includes('GYM_OWNER') : false

  return (
    <div className={styles.pageRoot}>
      <header className={styles.navbar}>
        <div className={styles.navLeft}>
          <a className={styles.logo} href="/" onClick={(e) => { e.preventDefault(); navigate('/') }}>
            FitiGo
          </a>
          <span className={styles.subtle}>Owner Portal</span>
        </div>

        <div className={styles.navRight}>
          <button
            type="button"
            className={`${styles.navBtn} ${active === 'dashboard' ? styles.navBtnActive : ''}`}
            onClick={() => navigate('/owner')}
          >
            Dashboard
          </button>
          <button
            type="button"
            className={`${styles.navBtn} ${active === 'gyms' ? styles.navBtnActive : ''}`}
            onClick={() => navigate('/owner/gyms')}
          >
            My Gyms
          </button>

          <button type="button" className={styles.navBtn} onClick={() => navigate('/profile')}>
            Profile
          </button>
          <button
            type="button"
            className={styles.navBtn}
            onClick={() => {
              clearTokens()
              navigate('/owner/login')
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
            <div className={styles.subtle}>Manage your gyms, bookings, staff, media and slots.</div>
          </div>
          <button type="button" className={styles.linkBtn} onClick={() => navigate('/')}>
            Back to consumer app
          </button>
        </div>

        {roles.status === 'loading' ? (
          <div className={styles.panel}>Loading…</div>
        ) : roles.status === 'error' ? (
          <div className={styles.panel}>Error: {roles.message}</div>
        ) : !hasOwnerRole ? (
          <div className={styles.panel}>
            <div className={styles.panelTitle}>Access denied</div>
            <div className={styles.subtle}>Your account is not a Gym Owner. Register as a Gym Owner to continue.</div>
            <div style={{ height: 10 }} />
            <button type="button" className={styles.primaryBtn} onClick={() => navigate('/owner/register')}>
              Register as Gym Owner
            </button>
          </div>
        ) : (
          children
        )}
      </main>
    </div>
  )
}
