import { useEffect, useState } from 'react'
import AdminLayout from './AdminLayout'
import styles from './admin.module.css'
import { adminApproveGym, adminReactivateGym, adminRejectGym, adminSetGymFeatured, adminSuspendGym, fetchAdminGyms, fetchPendingGyms, type AdminGymListItem } from './api'

export default function AdminGymsPage() {
  const [pending, setPending] = useState<{ status: 'loading' } | { status: 'ready'; data: AdminGymListItem[] } | { status: 'error'; message: string }>({ status: 'loading' })

  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [all, setAll] = useState<{ status: 'loading' } | { status: 'ready'; data: AdminGymListItem[] } | { status: 'error'; message: string }>({ status: 'loading' })

  const reload = () => {
    setPending({ status: 'loading' })
    fetchPendingGyms()
      .then((d) => setPending({ status: 'ready', data: d }))
      .catch((e) => setPending({ status: 'error', message: e?.message ?? 'Failed to load pending gyms' }))

    setAll({ status: 'loading' })
    fetchAdminGyms({ q: q.trim() || undefined, status: status.trim() || undefined, limit: 50, offset: 0 })
      .then((d) => setAll({ status: 'ready', data: d }))
      .catch((e) => setAll({ status: 'error', message: e?.message ?? 'Failed to load gyms' }))
  }

  useEffect(() => {
    reload()
  }, [])

  return (
    <AdminLayout title="Gyms" active="gyms">
      <div className={styles.panel}>
        <div className={styles.panelTitle}>Pending approvals</div>
        {pending.status === 'loading' ? (
          <div className={styles.subtle}>Loading…</div>
        ) : pending.status === 'error' ? (
          <div style={{ color: '#b91c1c', fontWeight: 700 }}>Error: {pending.message}</div>
        ) : pending.data.length === 0 ? (
          <div className={styles.subtle}>No gyms pending approval.</div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Gym</th>
                <th>City</th>
                <th>Status</th>
                <th>Active</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {pending.data.map((g) => (
                <tr key={g.id}>
                  <td>
                    <div style={{ fontWeight: 850 }}>{g.name}</div>
                    <div className={styles.subtle}>ID: {g.id}</div>
                  </td>
                  <td>{g.city ?? '—'}</td>
                  <td>
                    <span className={styles.tag}>{g.status}</span>
                  </td>
                  <td>{g.is_active ? 'Yes' : 'No'}</td>
                  <td>
                    <div className={styles.row}>
                      <button
                        type="button"
                        className={styles.primaryBtn}
                        onClick={async () => {
                          await adminApproveGym(g.id)
                          reload()
                        }}
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        className={styles.dangerBtn}
                        onClick={async () => {
                          const reason = prompt('Reject reason (required)') || ''
                          if (reason.trim().length < 3) return
                          await adminRejectGym(g.id, reason.trim())
                          reload()
                        }}
                      >
                        Reject
                      </button>
                      <button
                        type="button"
                        className={styles.secondaryBtn}
                        onClick={async () => {
                          const reason = prompt('Suspend reason (required)') || ''
                          if (reason.trim().length < 3) return
                          await adminSuspendGym(g.id, reason.trim())
                          reload()
                        }}
                      >
                        Suspend
                      </button>
                      <button
                        type="button"
                        className={styles.secondaryBtn}
                        onClick={async () => {
                          await adminReactivateGym(g.id)
                          reload()
                        }}
                      >
                        Reactivate
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div style={{ height: 14 }} />

      <div className={styles.panel}>
        <div className={styles.panelTitle}>All gyms</div>
        <div className={styles.row} style={{ marginBottom: 10 }}>
          <input className={styles.input} style={{ flex: 2, minWidth: 220 }} placeholder="Search gym name / city" value={q} onChange={(e) => setQ(e.target.value)} />
          <input className={styles.input} style={{ flex: 1, minWidth: 180 }} placeholder="Status (APPROVED/PENDING_APPROVAL)" value={status} onChange={(e) => setStatus(e.target.value)} />
          <button type="button" className={styles.primaryBtn} onClick={reload}>
            Apply
          </button>
        </div>

        {all.status === 'loading' ? (
          <div className={styles.subtle}>Loading…</div>
        ) : all.status === 'error' ? (
          <div style={{ color: '#b91c1c', fontWeight: 700 }}>Error: {all.message}</div>
        ) : all.data.length === 0 ? (
          <div className={styles.subtle}>No gyms found.</div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Gym</th>
                <th>City</th>
                <th>Status</th>
                <th>Featured</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {all.data.map((g) => (
                <tr key={g.id}>
                  <td>
                    <div style={{ fontWeight: 850 }}>{g.name}</div>
                    <div className={styles.subtle}>ID: {g.id}{typeof g.owner_user_id === 'number' ? ` • Owner: ${g.owner_user_id}` : ''}</div>
                  </td>
                  <td>{g.city ?? '—'}</td>
                  <td>
                    <span className={styles.tag}>{g.status}</span>
                  </td>
                  <td>{g.is_featured ? 'Yes' : 'No'}</td>
                  <td>
                    <div className={styles.row}>
                      <button
                        type="button"
                        className={styles.secondaryBtn}
                        onClick={async () => {
                          await adminSetGymFeatured(g.id, !Boolean(g.is_featured))
                          reload()
                        }}
                      >
                        {g.is_featured ? 'Unfeature' : 'Feature'}
                      </button>
                      <button
                        type="button"
                        className={styles.secondaryBtn}
                        onClick={async () => {
                          const reason = prompt('Suspend reason (required)') || ''
                          if (reason.trim().length < 3) return
                          await adminSuspendGym(g.id, reason.trim())
                          reload()
                        }}
                      >
                        Suspend
                      </button>
                      <button
                        type="button"
                        className={styles.secondaryBtn}
                        onClick={async () => {
                          await adminReactivateGym(g.id)
                          reload()
                        }}
                      >
                        Reactivate
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </AdminLayout>
  )
}
