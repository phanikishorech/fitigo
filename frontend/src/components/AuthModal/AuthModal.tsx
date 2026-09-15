import { useEffect, useMemo, useRef, useState } from 'react'
import styles from './authModal.module.css'
import { maskEmail } from './masking'
import { isValidEmail } from './validation'
import { EmailOtpPanel } from './EmailOtpPanel'
import { OtpVerifyPanel } from './OtpVerifyPanel'
import { MobileOtpPanel } from './MobileOtpPanel'

export type AuthUser = {
  id: number
  first_name: string | null
  last_name: string | null
  email: string
  phone: string | null
  status: string
  created_at: string
}

export type AuthResult = {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
  user: AuthUser
}

type Props = {
  open: boolean
  onClose: () => void
  onAuthed: (result: AuthResult) => void
  intent?: string | null
}

type Method = 'email' | 'mobile'
type Step = 'enter' | 'otp'

export default function AuthModal({ open, onClose, onAuthed }: Props) {
  const modalRef = useRef<HTMLDivElement | null>(null)
  const lastFocusedRef = useRef<HTMLElement | null>(null)

  // Keep mounted briefly to allow smooth exit animation.
  const [mounted, setMounted] = useState(open)
  const [closing, setClosing] = useState(false)

  const [method, setMethod] = useState<Method>('email')
  const [step, setStep] = useState<Step>('enter')
  const [email, setEmail] = useState('')
  const [mobile, setMobile] = useState({ countryCode: '+1', number: '' })
  const [otpTarget, setOtpTarget] = useState<
    | { kind: 'email'; email: string }
    | { kind: 'mobile'; countryCode: string; number: string }
    | null
  >(null)

  const maskedEmail = useMemo(() => maskEmail(email), [email])

  useEffect(() => {
    if (open) {
      setMounted(true)
      setClosing(false)
      return
    }

    if (!mounted) return
    setClosing(true)
    const t = window.setTimeout(() => {
      setMounted(false)
      setClosing(false)
    }, 170)
    return () => window.clearTimeout(t)
  }, [open, mounted])

  // Lock body scroll + restore focus.
  useEffect(() => {
    if (!open) return
    lastFocusedRef.current = document.activeElement as HTMLElement
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prevOverflow
      lastFocusedRef.current?.focus?.()
    }
  }, [open])

  // ESC to close + focus trap.
  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()

      if (e.key === 'Tab' && modalRef.current) {
        const focusables = Array.from(
          modalRef.current.querySelectorAll<HTMLElement>(
            'button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])'
          )
        ).filter((el) => !el.hasAttribute('disabled') && !el.getAttribute('aria-hidden'))
        if (focusables.length === 0) return

        const first = focusables[0]
        const last = focusables[focusables.length - 1]
        const active = document.activeElement

        if (e.shiftKey) {
          if (active === first || active === modalRef.current) {
            e.preventDefault()
            last.focus()
          }
        } else {
          if (active === last) {
            e.preventDefault()
            first.focus()
          }
        }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  // Reset state when closed.
  useEffect(() => {
    if (open) return
    setMethod('email')
    setStep('enter')
    setEmail('')
    setMobile({ countryCode: '+1', number: '' })
    setOtpTarget(null)
  }, [open])

  useEffect(() => {
    if (!open) return
    const t = window.setTimeout(() => {
      const el = modalRef.current?.querySelector<HTMLElement>('input')
      el?.focus?.()
    }, 0)
    return () => window.clearTimeout(t)
  }, [open, method, step])

  if (!mounted) return null

  return (
    <div
      className={`${styles.overlay} ${closing ? styles.overlayClosing : ''}`}
      role="presentation"
      onMouseDown={(e) => {
        if (closing) return
        // Click outside closes (matches reference). We only close when the overlay itself
        // is the click target to avoid interfering with form interactions.
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        ref={modalRef}
        className={`${styles.modal} ${closing ? styles.modalClosing : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-modal-title"
      >
        <div className={styles.leftPanel} aria-hidden="true">
          <div className={styles.mapBg} />
          <div className={styles.leftContent}>
            <div className={styles.heroCircle}>
              <div className={styles.heroPhoto} aria-hidden="true" />
            </div>

            <div className={styles.avatarA}>
              <div className={styles.avatarImg} />
              <div className={styles.bubble}>I’m working out nearby! 💪</div>
            </div>

            <div className={styles.avatarB}>
              <div className={styles.avatarImg2} />
              <div className={styles.bubble}>Gym session today?</div>
            </div>

            <div className={styles.avatarC}>
              <div className={styles.avatarImg3} />
              <div className={styles.bubble}>Join me for yoga 🧘</div>
            </div>

            <div className={styles.avatarD}>
              <div className={styles.avatarImg4} />
              <div className={styles.bubble}>New gym in your area!</div>
            </div>

            <div className={styles.avatarE}>
              <div className={styles.avatarImg5} />
              <div className={styles.bubble}>Available for training</div>
            </div>

            <div className={styles.avatarF}>
              <div className={styles.avatarImg6} />
              <div className={styles.bubble}>Let’s train together!</div>
            </div>

            <div className={styles.avatarG}>
              <div className={styles.avatarImg7} />
              <div className={styles.bubble}>Try this workout!</div>
            </div>

            <div className={styles.leftCaption}>
              Discover gyms, workouts, trainers, and members near your location.
            </div>
          </div>
        </div>

        <div className={styles.rightPanel}>
          <div className={styles.headerRow}>
            <div className={styles.title} id="auth-modal-title">
              Login / Sign Up
            </div>
            <button
              type="button"
              className={styles.closeBtn}
              onClick={onClose}
              aria-label="Close authentication modal"
            >
              <span aria-hidden="true">×</span>
            </button>
          </div>

          <div className={styles.divider} />

          {step === 'enter' && method === 'email' && (
            <EmailOtpPanel
              email={email}
              onEmailChange={setEmail}
              onSendOtp={async () => {
                const clean = email.trim().toLowerCase()
                if (!isValidEmail(clean)) return

                await fetch('/api/v1/auth/email/send-otp', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ email: clean })
                }).then(async (r) => {
                  if (!r.ok) {
                    const data = await r.json().catch(() => ({}))
                    throw new Error(data?.detail ?? 'Failed to send OTP')
                  }
                })

                setOtpTarget({ kind: 'email', email: clean })
                setStep('otp')
              }}
              onPickMobile={() => {
                setMethod('mobile')
                setStep('enter')
              }}
              onPickGoogle={async () => {
                window.alert('Google login is not wired yet. (Next: OAuth)')
              }}
            />
          )}

          {step === 'enter' && method === 'mobile' && (
            <MobileOtpPanel
              value={mobile}
              onChange={setMobile}
              onBackToEmail={() => {
                setMethod('email')
                setStep('enter')
              }}
              onSendOtp={async () => {
                const cc = mobile.countryCode.trim()
                const num = mobile.number.replace(/\s+/g, '')
                if (!cc || !num) return

                await fetch('/api/v1/auth/mobile/send-otp', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ country_code: cc, mobile_number: num })
                }).then(async (r) => {
                  if (!r.ok) {
                    const data = await r.json().catch(() => ({}))
                    throw new Error(data?.detail ?? 'Failed to send OTP')
                  }
                })

                setOtpTarget({ kind: 'mobile', countryCode: cc, number: num })
                setStep('otp')
              }}
            />
          )}

          {step === 'otp' && otpTarget?.kind === 'email' && (
            <OtpVerifyPanel
              title="Verify your email"
              subtitle="We've sent a verification code to your email address."
              maskedTarget={maskedEmail}
              onChangeTarget={() => {
                setStep('enter')
                setOtpTarget(null)
              }}
              onResend={async () => {
                await fetch('/api/v1/auth/email/send-otp', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ email: otpTarget.email })
                }).then(async (r) => {
                  if (!r.ok) {
                    const data = await r.json().catch(() => ({}))
                    throw new Error(data?.detail ?? 'Failed to resend OTP')
                  }
                })
              }}
              onVerify={async (otp) => {
                const result = await fetch('/api/v1/auth/email/verify-otp', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ email: otpTarget.email, otp })
                }).then(async (r) => {
                  const data = await r.json().catch(() => ({}))
                  if (!r.ok) throw new Error(data?.detail ?? 'OTP verification failed')
                  return data as AuthResult
                })
                onAuthed(result)
              }}
            />
          )}

          {step === 'otp' && otpTarget?.kind === 'mobile' && (
            <OtpVerifyPanel
              title="Verify your mobile"
              subtitle="We've sent a verification code to your phone number."
              maskedTarget={`${otpTarget.countryCode} •••• ${otpTarget.number.slice(-2)}`}
              onChangeTarget={() => {
                setStep('enter')
                setOtpTarget(null)
              }}
              onResend={async () => {
                await fetch('/api/v1/auth/mobile/send-otp', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    country_code: otpTarget.countryCode,
                    mobile_number: otpTarget.number
                  })
                }).then(async (r) => {
                  if (!r.ok) {
                    const data = await r.json().catch(() => ({}))
                    throw new Error(data?.detail ?? 'Failed to resend OTP')
                  }
                })
              }}
              onVerify={async (otp) => {
                const result = await fetch('/api/v1/auth/mobile/verify-otp', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    country_code: otpTarget.countryCode,
                    mobile_number: otpTarget.number,
                    otp
                  })
                }).then(async (r) => {
                  const data = await r.json().catch(() => ({}))
                  if (!r.ok) throw new Error(data?.detail ?? 'OTP verification failed')
                  return data as AuthResult
                })
                onAuthed(result)
              }}
            />
          )}
        </div>
      </div>
    </div>
  )
}
