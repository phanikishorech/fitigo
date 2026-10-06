import { logoutSession } from '../../session/store'
import { ReactNode } from 'react'
import styles from './admin.module.css'
import { navigate } from '../../router'
import { useIdentity } from '../../session/SessionGuard'


export default function AdminLayout({ title, children, active }: { title: string; children: ReactNode; active: 'dashboard' | 'users' | 'gyms' | 'bookings' }) {
  useIdentity() // Central route guard owns session and portal permissions.

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
              void logoutSession()
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

        {children}
      </main>
    </div>
  )
}
