import { useEffect, useState } from 'react'
import AdminLayout from './AdminLayout'
import styles from './admin.module.css'
import { fetchAdminDashboardSummary, type AdminDashboardSummary } from './api'

export default function AdminDashboardPage() {
  const [summary, setSummary] = useState<{ status: 'loading' } | { status: 'ready'; data: AdminDashboardSummary } | { status: 'error'; message: string }>({ status: 'loading' })

  const reload = () => {
    setSummary({ status: 'loading' })
    fetchAdminDashboardSummary()
      .then((d) => setSummary({ status: 'ready', data: d }))
      .catch((e) => setSummary({ status: 'error', message: e?.message ?? 'Failed to load' }))
  }

  useEffect(() => {
    reload()
  }, [])

  return (
    <AdminLayout title="Admin Dashboard" active="dashboard">
      {summary.status === 'error' ? <div className={styles.panel}>Error: {summary.message}</div> : null}

      <div className={styles.cardGrid}>
        <div className={styles.card}>
          <div className={styles.subtle}>Users</div>
          <div className={styles.metric}>{summary.status === 'ready' ? summary.data.users.total : '—'}</div>
          <div className={styles.subtle}>Customers: {summary.status === 'ready' ? summary.data.users.customers : '—'} • Owners: {summary.status === 'ready' ? summary.data.users.gym_owners : '—'}</div>
        </div>
        <div className={styles.card}>
          <div className={styles.subtle}>Gyms</div>
          <div className={styles.metric}>{summary.status === 'ready' ? summary.data.gyms.total : '—'}</div>
          <div className={styles.subtle}>Pending approval: {summary.status === 'ready' ? summary.data.gyms.pending_approval : '—'}</div>
        </div>
        <div className={styles.card}>
          <div className={styles.subtle}>Bookings</div>
          <div className={styles.metric}>{summary.status === 'ready' ? summary.data.bookings.today : '—'}</div>
          <div className={styles.subtle}>Today • Upcoming: {summary.status === 'ready' ? summary.data.bookings.upcoming : '—'}</div>
        </div>
        <div className={styles.card}>
          <div className={styles.subtle}>Revenue</div>
          <div className={styles.metric}>{summary.status === 'ready' ? summary.data.revenue.last_30d : '—'}</div>
          <div className={styles.subtle}>Last 30 days ({summary.status === 'ready' ? summary.data.revenue.currency : 'INR'})</div>
        </div>
      </div>

      <div style={{ height: 14 }} />

      <div className={styles.panel}>
        <div className={styles.panelTitle}>Quick actions</div>
        <div className={styles.row}>
          <button type="button" className={styles.secondaryBtn} onClick={reload}>
            Refresh
          </button>
        </div>
      </div>
    </AdminLayout>
  )
}
