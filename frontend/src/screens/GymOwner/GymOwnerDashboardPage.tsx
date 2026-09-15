import { useEffect, useMemo, useState } from 'react'
import OwnerLayout from './OwnerLayout'
import styles from './gymOwner.module.css'
import { navigate } from '../../router'
import { createGymOwner, fetchOwnerGyms, fetchOwnerSummary, type OwnerDashboardSummary, type OwnerGymListItem } from './api'

type Props = { initialTab?: 'dashboard' | 'gyms' }

export default function GymOwnerDashboardPage({ initialTab }: Props) {
  const tab = initialTab ?? 'dashboard'

  const [summary, setSummary] = useState<{ status: 'loading' } | { status: 'ready'; data: OwnerDashboardSummary } | { status: 'error'; message: string }>({
    status: 'loading'
  })
  const [gyms, setGyms] = useState<{ status: 'loading' } | { status: 'ready'; data: OwnerGymListItem[] } | { status: 'error'; message: string }>({
    status: 'loading'
  })

  const [newGymName, setNewGymName] = useState('')
  const [newGymCity, setNewGymCity] = useState('')
  const [newGymPricePerPerson, setNewGymPricePerPerson] = useState('')
  const [creating, setCreating] = useState(false)

  const title = useMemo(() => (tab === 'gyms' ? 'My Gyms' : 'Owner Dashboard'), [tab])

  const reload = () => {
    setSummary({ status: 'loading' })
    setGyms({ status: 'loading' })
    fetchOwnerSummary()
      .then((d) => setSummary({ status: 'ready', data: d }))
      .catch((e) => setSummary({ status: 'error', message: e?.message ?? 'Failed to load' }))
    fetchOwnerGyms()
      .then((d) => setGyms({ status: 'ready', data: d }))
      .catch((e) => setGyms({ status: 'error', message: e?.message ?? 'Failed to load gyms' }))
  }

  useEffect(() => {
    reload()
  }, [])

  return (
    <OwnerLayout title={title} active={tab === 'gyms' ? 'gyms' : 'dashboard'}>
      {tab === 'dashboard' ? (
        <>
          <div className={styles.cardGrid}>
            <div className={styles.card}>
              <div className={styles.subtle}>Gyms</div>
              <div className={styles.metric}>{summary.status === 'ready' ? summary.data.gyms.total : '—'}</div>
              <div className={styles.subtle}>Approved: {summary.status === 'ready' ? summary.data.gyms.approved : '—'} • Pending: {summary.status === 'ready' ? summary.data.gyms.pending_approval : '—'}</div>
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
              <button type="button" className={styles.primaryBtn} onClick={() => navigate('/owner/gyms')}>
                Manage gyms
              </button>
              <button type="button" className={styles.secondaryBtn} onClick={reload}>
                Refresh
              </button>
            </div>
          </div>
        </>
      ) : null}

      <div style={{ height: 14 }} />

      <div className={styles.panel}>
        <div className={styles.panelTitle}>Your gyms</div>
        {gyms.status === 'loading' ? (
          <div className={styles.subtle}>Loading gyms…</div>
        ) : gyms.status === 'error' ? (
          <div style={{ color: '#b91c1c', fontWeight: 650 }}>{gyms.message}</div>
        ) : gyms.data.length === 0 ? (
          <div className={styles.subtle}>No gyms yet. Create your first gym below.</div>
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
              {gyms.data.map((g) => (
                <tr key={g.id}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      {g.cover_image_url ? (
                        <img src={g.cover_image_url} alt="" style={{ width: 48, height: 32, borderRadius: 8, objectFit: 'cover', border: '1px solid var(--line)' }} />
                      ) : (
                        <div style={{ width: 48, height: 32, borderRadius: 8, background: '#eef2ff', border: '1px solid var(--line)' }} />
                      )}
                      <div>
                        <div style={{ fontWeight: 800 }}>{g.name}</div>
                        <div className={styles.subtle}>ID: {g.id}</div>
                      </div>
                    </div>
                  </td>
                  <td>{g.city ?? '—'}</td>
                  <td>
                    <span className={styles.tag}>{g.status}</span>
                  </td>
                  <td>{g.is_active ? 'Yes' : 'No'}</td>
                  <td>
                    <button type="button" className={styles.linkBtn} onClick={() => navigate(`/owner/gyms/${g.id}`)}>
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div style={{ height: 14 }} />
        <div className={styles.panelTitle}>Create a gym</div>
        <div className={styles.row}>
          <input className={styles.input} style={{ flex: 2, minWidth: 220 }} placeholder="Gym name" value={newGymName} onChange={(e) => setNewGymName(e.target.value)} />
          <input className={styles.input} style={{ flex: 1, minWidth: 160 }} placeholder="City" value={newGymCity} onChange={(e) => setNewGymCity(e.target.value)} />
          <input
            className={styles.input}
            style={{ flex: 1, minWidth: 180 }}
            placeholder="Price per person (₹)"
            inputMode="decimal"
            value={newGymPricePerPerson}
            onChange={(e) => setNewGymPricePerPerson(e.target.value)}
          />
          <button
            type="button"
            className={styles.primaryBtn}
            disabled={creating || newGymName.trim().length < 2}
            onClick={async () => {
              setCreating(true)
              try {
                const created = await createGymOwner({
                  name: newGymName.trim(),
                  city: newGymCity.trim() || null,
                  gym_price_per_person: newGymPricePerPerson.trim() ? newGymPricePerPerson.trim() : undefined
                })
                setNewGymName('')
                setNewGymCity('')
                setNewGymPricePerPerson('')
                navigate(`/owner/gyms/${created.id}`)
              } catch (e: any) {
                alert(e?.message ?? 'Failed to create')
              } finally {
                setCreating(false)
                reload()
              }
            }}
          >
            {creating ? 'Creating…' : 'Create'}
          </button>
        </div>
      </div>
    </OwnerLayout>
  )
}
