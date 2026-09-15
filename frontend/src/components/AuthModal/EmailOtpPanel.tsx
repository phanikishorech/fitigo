import { useMemo, useState } from 'react'
import panel from './panel.module.css'
import { isValidEmail } from './validation'

type Props = {
  email: string
  onEmailChange: (v: string) => void
  onSendOtp: () => Promise<void>
  onPickMobile: () => void
  onPickGoogle: () => Promise<void>
}

export function EmailOtpPanel({ email, onEmailChange, onSendOtp, onPickMobile, onPickGoogle }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [touched, setTouched] = useState(false)

  const clean = useMemo(() => email.trim().toLowerCase(), [email])
  const valid = useMemo(() => isValidEmail(clean), [clean])

  return (
    <div className={panel.panel}>
      <div className={panel.label}>
        Enter email <span className={panel.required}>*</span>
      </div>

      <input
        className={panel.input}
        type="email"
        value={email}
        onChange={(e) => {
          onEmailChange(e.target.value)
          setError(null)
        }}
        onBlur={() => setTouched(true)}
        placeholder="Enter your email address"
        autoComplete="email"
        inputMode="email"
        aria-label="Email"
      />

      <div className={panel.errorText} role="alert" aria-live="polite">
        {error ?? (touched && !valid ? 'Please enter a valid email address.' : '')}
      </div>

      <button
        type="button"
        className={panel.primaryBtn}
        disabled={!valid || loading}
        onClick={async () => {
          if (loading) return
          if (!valid) {
            setTouched(true)
            setError('Please enter a valid email address.')
            return
          }
          setLoading(true)
          setError(null)
          try {
            await onSendOtp()
          } catch (e) {
            setError(e instanceof Error ? e.message : 'Failed to send OTP')
          } finally {
            setLoading(false)
          }
        }}
      >
        {loading ? 'Sending…' : 'Send OTP'}
      </button>

      <div className={panel.orRow} aria-hidden="true">
        <div className={panel.orLine} />
        <div className={panel.orText}>or</div>
        <div className={panel.orLine} />
      </div>

      <div className={panel.altMethods}>
        <button
          type="button"
          className={panel.altMethodBtn}
          onClick={onPickMobile}
          aria-label="Switch to mobile OTP login"
        >
          <div className={panel.iconCircle} aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M8 2h8a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z" stroke="#111827" strokeWidth="1.6" />
              <path d="M10 19h4" stroke="#111827" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </div>
          <div className={panel.altLabel}>Mobile</div>
        </button>

        <button
          type="button"
          className={panel.altMethodBtn}
          onClick={async () => {
            setLoading(true)
            setError(null)
            try {
              await onPickGoogle()
            } catch (e) {
              setError(e instanceof Error ? e.message : 'Google login failed')
            } finally {
              setLoading(false)
            }
          }}
          aria-label="Continue with Google"
        >
          <div className={panel.iconCircle} aria-hidden="true">
            <div style={{ fontWeight: 800, fontSize: 18, color: '#111827' }}>G</div>
          </div>
          <div className={panel.altLabel}>Google</div>
        </button>
      </div>

      <div className={panel.footerSpacer} />
    </div>
  )
}
