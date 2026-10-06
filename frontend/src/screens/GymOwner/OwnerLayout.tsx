import { logoutSession } from '../../session/store'
import { ReactNode } from 'react'
import styles from './gymOwner.module.css'
import { navigate } from '../../router'
import { useIdentity } from '../../session/SessionGuard'


export default function OwnerLayout({ title, children, active }: { title: string; children: ReactNode; active: 'dashboard' | 'gyms' }) {
  useIdentity() // Central route guard owns session and portal permissions.

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
            <div className={styles.subtle}>Manage your gyms, bookings, staff, media and slots.</div>
          </div>
          <button type="button" className={styles.linkBtn} onClick={() => navigate('/')}>
            Back to consumer app
          </button>
        </div>

        {children}
      </main>
    </div>
  )
}
