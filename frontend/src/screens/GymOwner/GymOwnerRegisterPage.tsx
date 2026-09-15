import { useState } from 'react'
import styles from './gymOwner.module.css'
import { navigate } from '../../router'

export default function GymOwnerRegisterPage() {
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  return (
    <div className={styles.pageRoot}>
      <div className={styles.content} style={{ maxWidth: 620, margin: '0 auto' }}>
        <div className={styles.panel}>
          <div className={styles.panelTitle}>Register Gym Owner</div>
          <div className={styles.subtle}>Create an owner account, then login to manage gyms.</div>
          <div style={{ height: 12 }} />

          <div className={styles.row}>
            <input className={styles.input} style={{ flex: 1 }} placeholder="First name" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
            <input className={styles.input} style={{ flex: 1 }} placeholder="Last name" value={lastName} onChange={(e) => setLastName(e.target.value)} />
          </div>
          <div style={{ height: 10 }} />
          <div className={styles.row}>
            <input className={styles.input} style={{ flex: 1 }} placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div style={{ height: 10 }} />
          <div className={styles.row}>
            <input
              className={styles.input}
              style={{ flex: 1 }}
              placeholder="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error ? (
            <div style={{ marginTop: 10, color: '#b91c1c', fontWeight: 650 }}>{error}</div>
          ) : null}
          <div style={{ height: 12 }} />
          <div className={styles.row}>
            <button
              type="button"
              className={styles.primaryBtn}
              disabled={busy}
              onClick={async () => {
                setError(null)
                setBusy(true)
                try {
                  const r = await fetch('/api/v1/auth/register/gym-owner', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                      first_name: firstName || 'Owner',
                      last_name: lastName || 'User',
                      email: email.trim().toLowerCase(),
                      phone: null,
                      password
                    })
                  })
                  const data = await r.json().catch(() => ({}))
                  if (!r.ok) throw new Error((data as any)?.detail ?? 'Registration failed')
                  navigate('/owner/login')
                } catch (e: any) {
                  setError(e?.message ?? 'Registration failed')
                } finally {
                  setBusy(false)
                }
              }}
            >
              {busy ? 'Creating…' : 'Create account'}
            </button>
            <button type="button" className={styles.linkBtn} onClick={() => navigate('/owner/login')}>
              I already have an account
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
