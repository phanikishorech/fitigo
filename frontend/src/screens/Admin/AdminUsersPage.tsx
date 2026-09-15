import { useEffect, useState } from 'react'
import AdminLayout from './AdminLayout'
import styles from './admin.module.css'
import { adminUpdateUserStatus, fetchAdminUsers, type AdminUserListItem } from './api'

export default function AdminUsersPage() {
  const [q, setQ] = useState('')
  const [role, setRole] = useState('')
  const [status, setStatus] = useState('')
  const [users, setUsers] = useState<{ status: 'loading' } | { status: 'ready'; data: AdminUserListItem[] } | { status: 'error'; message: string }>({ status: 'loading' })

  const reload = () => {
    setUsers({ status: 'loading' })
    fetchAdminUsers({ q: q.trim() || undefined, role: role.trim() || undefined, status: status.trim() || undefined })
      .then((d) => setUsers({ status: 'ready', data: d }))
      .catch((e) => setUsers({ status: 'error', message: e?.message ?? 'Failed to load users' }))
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <AdminLayout title="Users" active="users">
      <div className={styles.panel}>
        <div className={styles.panelTitle}>Search / filters</div>
        <div className={styles.row}>
          <input className={styles.input} style={{ flex: 2, minWidth: 220 }} placeholder="Search email/name/phone" value={q} onChange={(e) => setQ(e.target.value)} />
          <input className={styles.input} style={{ flex: 1, minWidth: 160 }} placeholder="Role (CUSTOMER/GYM_OWNER/ADMIN)" value={role} onChange={(e) => setRole(e.target.value)} />
          <input className={styles.input} style={{ flex: 1, minWidth: 160 }} placeholder="Status (ACTIVE/SUSPENDED)" value={status} onChange={(e) => setStatus(e.target.value)} />
          <button type="button" className={styles.primaryBtn} onClick={reload}>
            Apply
          </button>
        </div>
      </div>

      <div style={{ height: 14 }} />

      <div className={styles.panel}>
        <div className={styles.panelTitle}>All users</div>
        {users.status === 'loading' ? (
          <div className={styles.subtle}>Loading…</div>
        ) : users.status === 'error' ? (
          <div style={{ color: '#b91c1c', fontWeight: 700 }}>Error: {users.message}</div>
        ) : users.data.length === 0 ? (
          <div className={styles.subtle}>No users found.</div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>User</th>
                <th>Status</th>
                <th>Roles</th>
                <th>Created</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users.data.map((u) => (
                <tr key={u.id}>
                  <td>
                    <div style={{ fontWeight: 850 }}>{u.first_name || u.last_name ? `${u.first_name ?? ''} ${u.last_name ?? ''}`.trim() : '—'}</div>
                    <div className={styles.subtle}>{u.email}</div>
                    <div className={styles.subtle}>ID: {u.id}{u.phone ? ` • ${u.phone}` : ''}</div>
                  </td>
                  <td>
                    <span className={styles.tag}>{u.status}</span>
                  </td>
                  <td>{u.roles?.length ? u.roles.join(', ') : '—'}</td>
                  <td>{new Date(u.created_at).toLocaleString()}</td>
                  <td>
                    <div className={styles.row}>
                      <button
                        type="button"
                        className={styles.secondaryBtn}
                        onClick={async () => {
                          const newStatus = prompt('Set status (ACTIVE/INACTIVE/SUSPENDED)', u.status) || ''
                          if (!newStatus.trim()) return
                          await adminUpdateUserStatus(u.id, { status: newStatus.trim().toUpperCase() })
                          reload()
                        }}
                      >
                        Update status
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
