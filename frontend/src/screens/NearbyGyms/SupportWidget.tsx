import { useEffect, useRef, useState } from 'react'
import styles from './nearbyGyms.module.css'

export default function SupportWidget() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!ref.current) return
      if (!ref.current.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', onDown)
    return () => window.removeEventListener('mousedown', onDown)
  }, [open])

  return (
    <div className={styles.supportWrap} ref={ref}>
      {open ? (
        <div className={styles.supportPanel} role="dialog" aria-label="Support">
          <div className={styles.supportTitle}>Need help?</div>
          <div className={styles.supportList}>
            <button
              type="button"
              className={styles.supportItem}
              onClick={() => window.alert('Chat support is not wired yet.')}
            >
              Chat Support
            </button>
            <button
              type="button"
              className={styles.supportItem}
              onClick={() => window.alert('Membership help is not wired yet.')}
            >
              Membership Help
            </button>
            <button
              type="button"
              className={styles.supportItem}
              onClick={() => window.alert('Gym access issue is not wired yet.')}
            >
              Gym Access Issue
            </button>
            <button
              type="button"
              className={styles.supportItem}
              onClick={() => window.alert('Payment support is not wired yet.')}
            >
              Payment Issue
            </button>
            <button
              type="button"
              className={styles.supportItem}
              onClick={() => window.alert('FAQ is not wired yet.')}
            >
              Frequently Asked Questions
            </button>
          </div>
        </div>
      ) : null}

      <button
        type="button"
        className={styles.supportBtn}
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? 'Close support' : 'Open support'}
      >
        <span className={styles.supportBtnText}>Need help?</span>
      </button>
    </div>
  )
}
