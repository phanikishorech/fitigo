import { useMemo, useState } from 'react'
import panel from './panel.module.css'

type Value = { countryCode: string; number: string }

type Props = {
  value: Value
  onChange: (v: Value) => void
  onSendOtp: () => Promise<void>
  onBackToEmail: () => void
}

export function MobileOtpPanel({ value, onChange, onSendOtp, onBackToEmail }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [touched, setTouched] = useState(false)

  const valid = useMemo(() => {
    const cc = value.countryCode.trim()
    const num = value.number.replace(/\s+/g, '')
    return /^\+\d{1,4}$/.test(cc) && /^\d{6,15}$/.test(num)
  }, [value.countryCode, value.number])

  return (
    <div className={panel.panel}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div className={panel.label} style={{ marginTop: 0 }}>
          Enter mobile <span className={panel.required}>*</span>
        </div>
        <button className={panel.secondaryLink} type="button" onClick={onBackToEmail}>
          Use email
        </button>
      </div>

      <div className={panel.row}>
        <input
          className={panel.input}
          value={value.countryCode}
          onChange={(e) => {
            onChange({ ...value, countryCode: e.target.value })
            setError(null)
          }}
          onBlur={() => setTouched(true)}
          placeholder="+1"
          aria-label="Country code"
          inputMode="tel"
        />
        <input
          className={panel.input}
          value={value.number}
          onChange={(e) => {
            onChange({ ...value, number: e.target.value })
            setError(null)
          }}
          onBlur={() => setTouched(true)}
          placeholder="Mobile number"
          aria-label="Mobile number"
          inputMode="tel"
          autoComplete="tel"
        />
      </div>

      <div className={panel.errorText} role="alert" aria-live="polite">
        {error ?? (touched && !valid ? 'Enter a valid country code and mobile number.' : '')}
      </div>

      <button
        type="button"
        className={panel.primaryBtn}
        disabled={!valid || loading}
        onClick={async () => {
          if (loading) return
          if (!valid) {
            setTouched(true)
            setError('Enter a valid country code and mobile number.')
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

      <div className={panel.footerSpacer} />
    </div>
  )
}
