import { useState } from 'react'
import styles from './gymOwner.module.css'
import { navigate } from '../../router'
import { setTokens } from '../../auth'

export default function GymOwnerLoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  return (
    <div className={styles.pageRoot}>
      <div className={styles.content} style={{ maxWidth: 520, margin: '0 auto' }}>
        <div className={styles.panel}>
          <div className={styles.panelTitle}>Gym Owner Login</div>
          <div className={styles.subtle}>Use your email/password (Gym Owner account).</div>
          <div style={{ height: 12 }} />

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
                  const r = await fetch('/api/v1/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: email.trim().toLowerCase(), password })
                  })
                  const data = await r.json().catch(() => ({}))
                  if (!r.ok) throw new Error((data as any)?.detail ?? 'Login failed')
                  setTokens((data as any).access_token, (data as any).refresh_token)
                  navigate('/owner')
                } catch (e: any) {
                  setError(e?.message ?? 'Login failed')
                } finally {
                  setBusy(false)
                }
              }}
            >
              {busy ? 'Logging in…' : 'Login'}
            </button>
            <button type="button" className={styles.linkBtn} onClick={() => navigate('/owner/register')}>
              Create owner account
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
