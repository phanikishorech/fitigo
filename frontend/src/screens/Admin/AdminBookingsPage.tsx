import { useEffect, useState } from 'react'
import AdminLayout from './AdminLayout'
import styles from './admin.module.css'
import { adminCancelBooking, fetchAdminBookings, type AdminBooking } from './api'

export default function AdminBookingsPage() {
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [paymentStatus, setPaymentStatus] = useState('')
  const [date, setDate] = useState('')

  const [items, setItems] = useState<{ status: 'loading' } | { status: 'ready'; data: AdminBooking[] } | { status: 'error'; message: string }>({ status: 'loading' })

  const reload = () => {
    setItems({ status: 'loading' })
    fetchAdminBookings({
      q: q.trim() || undefined,
      status: status.trim() || undefined,
      payment_status: paymentStatus.trim() || undefined,
      date: date.trim() || undefined,
      limit: 50,
      offset: 0
    })
      .then((d) => setItems({ status: 'ready', data: d }))
      .catch((e) => setItems({ status: 'error', message: e?.message ?? 'Failed to load bookings' }))
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <AdminLayout title="Bookings" active="bookings">
      <div className={styles.panel}>
        <div className={styles.panelTitle}>Search / filters</div>
        <div className={styles.row}>
          <input className={styles.input} style={{ flex: 2, minWidth: 220 }} placeholder="Search customer/gym/name/city" value={q} onChange={(e) => setQ(e.target.value)} />
          <input className={styles.input} style={{ flex: 1, minWidth: 160 }} placeholder="Status (CONFIRMED/CANCELLED)" value={status} onChange={(e) => setStatus(e.target.value)} />
          <input className={styles.input} style={{ flex: 1, minWidth: 160 }} placeholder="Payment (PAID/FAILED)" value={paymentStatus} onChange={(e) => setPaymentStatus(e.target.value)} />
          <input className={styles.input} style={{ flex: 1, minWidth: 150 }} placeholder="Date (YYYY-MM-DD)" value={date} onChange={(e) => setDate(e.target.value)} />
          <button type="button" className={styles.primaryBtn} onClick={reload}>
            Apply
          </button>
        </div>
      </div>

      <div style={{ height: 14 }} />

      <div className={styles.panel}>
        <div className={styles.panelTitle}>Recent bookings</div>
        {items.status === 'loading' ? (
          <div className={styles.subtle}>Loading…</div>
        ) : items.status === 'error' ? (
          <div style={{ color: '#b91c1c', fontWeight: 700 }}>Error: {items.message}</div>
        ) : items.data.length === 0 ? (
          <div className={styles.subtle}>No bookings found.</div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>ID</th>
                <th>When</th>
                <th>Gym / Slot</th>
                <th>Customer</th>
                <th>Status</th>
                <th>Payment</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.data.map((b) => (
                <tr key={b.id}>
                  <td>
                    <div style={{ fontWeight: 850 }}>#{b.id}</div>
                    <div className={styles.subtle}>{b.currency} {b.total_price}</div>
                  </td>
                  <td>{new Date(b.slot_date).toLocaleDateString()}</td>
                  <td>
                    <div style={{ fontWeight: 850 }}>{b.gym.name}</div>
                    <div className={styles.subtle}>{b.slot.name} ({b.slot.start_time} - {b.slot.end_time})</div>
                  </td>
                  <td>
                    <div style={{ fontWeight: 850 }}>{b.customer.first_name || b.customer.last_name ? `${b.customer.first_name ?? ''} ${b.customer.last_name ?? ''}`.trim() : '—'}</div>
                    <div className={styles.subtle}>{b.customer.email}</div>
                  </td>
                  <td>
                    <span className={styles.tag}>{b.status}</span>
                  </td>
                  <td>{b.payment ? `${b.payment.status} (${b.payment.provider})` : '—'}</td>
                  <td>
                    <button
                      type="button"
                      className={styles.dangerBtn}
                      onClick={async () => {
                        const reason = prompt('Cancel reason (required)') || ''
                        if (reason.trim().length < 3) return
                        await adminCancelBooking(b.id, reason.trim())
                        reload()
                      }}
                    >
                      Force cancel
                    </button>
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
