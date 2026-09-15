import { useEffect, useMemo, useRef, useState } from 'react'
import panel from './panel.module.css'

type Props = {
  title: string
  subtitle: string
  maskedTarget: string
  onChangeTarget: () => void
  onResend: () => Promise<void>
  onVerify: (otp: string) => Promise<void>
}

const OTP_LEN = 6

export function OtpVerifyPanel({ title, subtitle, maskedTarget, onChangeTarget, onResend, onVerify }: Props) {
  const [digits, setDigits] = useState<string[]>(Array.from({ length: OTP_LEN }, () => ''))
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resendIn, setResendIn] = useState(30)
  const inputsRef = useRef<Array<HTMLInputElement | null>>([])

  const otp = useMemo(() => digits.join(''), [digits])
  const complete = useMemo(() => digits.every((d) => d.length === 1), [digits])

  useEffect(() => {
    const t = window.setInterval(() => {
      setResendIn((s) => (s <= 0 ? 0 : s - 1))
    }, 1000)
    return () => window.clearInterval(t)
  }, [])

  useEffect(() => {
    inputsRef.current[0]?.focus?.()
  }, [])

  return (
    <div className={panel.panel}>
      <div className={panel.otpHeader}>
        <div className={panel.otpTitle}>{title}</div>
        <div className={panel.otpSub}>
          {subtitle} <span className={panel.maskedTarget}>{maskedTarget}</span>
        </div>
        <button type="button" className={panel.secondaryLink} onClick={onChangeTarget}>
          Change
        </button>
      </div>

      <div className={panel.otpBoxes} aria-label="One-time passcode">
        {digits.map((d, idx) => (
          <input
            key={idx}
            ref={(el) => {
              inputsRef.current[idx] = el
            }}
            className={`${panel.otpBox} ${error ? panel.otpBoxError : ''}`}
            value={d}
            inputMode="numeric"
            autoComplete={idx === 0 ? 'one-time-code' : 'off'}
            aria-label={`OTP digit ${idx + 1}`}
            onChange={(e) => {
              setError(null)
              const raw = e.target.value
              const onlyDigits = raw.replace(/\D/g, '')
              if (onlyDigits.length === 0) {
                const next = [...digits]
                next[idx] = ''
                setDigits(next)
                return
              }
              const next = [...digits]
              next[idx] = onlyDigits[onlyDigits.length - 1]
              setDigits(next)
              if (idx < OTP_LEN - 1) inputsRef.current[idx + 1]?.focus?.()
            }}
            onKeyDown={(e) => {
              if (e.key === 'Backspace') {
                if (digits[idx]) {
                  const next = [...digits]
                  next[idx] = ''
                  setDigits(next)
                  return
                }
                if (idx > 0) inputsRef.current[idx - 1]?.focus?.()
              }
              if (e.key === 'ArrowLeft' && idx > 0) inputsRef.current[idx - 1]?.focus?.()
              if (e.key === 'ArrowRight' && idx < OTP_LEN - 1) inputsRef.current[idx + 1]?.focus?.()
            }}
            onPaste={(e) => {
              const text = e.clipboardData.getData('text')
              const digitsOnly = text.replace(/\D/g, '').slice(0, OTP_LEN)
              if (digitsOnly.length === 0) return
              e.preventDefault()
              const next = Array.from({ length: OTP_LEN }, (_, i) => digitsOnly[i] ?? '')
              setDigits(next)
              if (digitsOnly.length === OTP_LEN) inputsRef.current[OTP_LEN - 1]?.focus?.()
              else inputsRef.current[digitsOnly.length]?.focus?.()
            }}
            maxLength={1}
          />
        ))}
      </div>

      <div className={panel.errorText} role="alert" aria-live="polite">
        {error}
      </div>

      <button
        type="button"
        className={panel.primaryBtn}
        disabled={!complete || submitting}
        onClick={async () => {
          if (!complete || submitting) return
          setSubmitting(true)
          setError(null)
          try {
            await onVerify(otp)
          } catch (e) {
            setError(e instanceof Error ? e.message : 'Invalid OTP')
            setDigits(Array.from({ length: OTP_LEN }, () => ''))
            inputsRef.current[0]?.focus?.()
          } finally {
            setSubmitting(false)
          }
        }}
      >
        {submitting ? 'Verifying…' : 'Verify & Continue'}
      </button>

      <div className={panel.resendRow}>
        <div className={panel.resendText}>Didn't receive the code?</div>
        <button
          type="button"
          className={panel.resendBtn}
          disabled={resendIn > 0}
          onClick={async () => {
            if (resendIn > 0) return
            setError(null)
            try {
              await onResend()
              setResendIn(30)
            } catch (e) {
              setError(e instanceof Error ? e.message : 'Failed to resend OTP')
            }
          }}
        >
          Resend OTP{resendIn > 0 ? ` (${resendIn}s)` : ''}
        </button>
      </div>

      <div className={panel.footerSpacer} />
    </div>
  )
}
