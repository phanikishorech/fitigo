import { useEffect, useMemo, useState } from 'react'
import styles from './nearbyGyms.module.css'
import { fetchAppLinks } from './api'

type Props = {
  open: boolean
  onClose: () => void
}

export default function AppDownloadModal({ open, onClose }: Props) {
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [links, setLinks] = useState<{ android: string | null; ios: string | null } | null>(null)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    setErr(null)
    fetchAppLinks()
      .then((data) => setLinks(data))
      .catch((e) => setErr(e?.message ?? 'Failed to load app links'))
      .finally(() => setLoading(false))
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  const qrText = useMemo(() => {
    const url = links?.android ?? links?.ios
    return url || ''
  }, [links?.android, links?.ios])

  if (!open) return null

  return (
    <div className={styles.lpOverlay} role="presentation" onMouseDown={onClose}>
      <div className={styles.lpModal} role="dialog" aria-modal="true" aria-label="Get the app" onMouseDown={(e) => e.stopPropagation()}>
        <div className={styles.lpHeader}>
          <div style={{ fontWeight: 700, fontSize: 16 }}>Get the App</div>
          <button type="button" className={styles.iconBtn} onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className={styles.lpBody}>
          <div style={{ color: 'var(--muted)', lineHeight: 1.5, marginBottom: 14 }}>
            Download Fitigo to manage your membership, access gyms, and get faster check-ins.
          </div>

          {loading ? <div className={styles.inlineInfo}>Loading links…</div> : null}
          {err ? <div className={styles.inlineError}>{err}</div> : null}

          <div className={styles.appLinksGrid}>
            <a
              className={styles.appLinkCard}
              href={links?.android ?? '#'}
              onClick={(e) => {
                if (!links?.android) e.preventDefault()
              }}
              aria-disabled={!links?.android}
            >
              <div className={styles.appLinkTitle}>Android</div>
              <div className={styles.appLinkSub}>{links?.android ? 'Open Play Store' : 'Coming soon'}</div>
            </a>

            <a
              className={styles.appLinkCard}
              href={links?.ios ?? '#'}
              onClick={(e) => {
                if (!links?.ios) e.preventDefault()
              }}
              aria-disabled={!links?.ios}
            >
              <div className={styles.appLinkTitle}>iOS</div>
              <div className={styles.appLinkSub}>{links?.ios ? 'Open App Store' : 'Coming soon'}</div>
            </a>
          </div>

          <div className={styles.qrBlock}>
            <div style={{ fontWeight: 650, marginBottom: 8 }}>Scan QR</div>
            <div className={styles.qrPlaceholder} aria-label="QR code placeholder">
              <div className={styles.qrInner}>
                <div style={{ fontWeight: 700 }}>QR</div>
                <div style={{ fontSize: 12, color: 'var(--muted)', textAlign: 'center' }}>
                  {qrText ? 'Generated from app link' : 'Configure app links in backend env'}
                </div>
              </div>
            </div>
            <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 8 }}>
              {qrText ? qrText : 'Set ANDROID_APP_URL / IOS_APP_URL in backend .env'}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
