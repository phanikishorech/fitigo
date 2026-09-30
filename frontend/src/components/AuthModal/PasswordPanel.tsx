import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { authService } from '../../services/authService'
import type { AuthTokens } from './AuthModal'
import { isValidEmail } from './validation'
import panel from './panel.module.css'

type Props = {
  email: string
  onEmailChange: (email: string) => void
  onAuthed: (result: AuthTokens) => void
  onBusyChange: (busy: boolean) => void
}

export function PasswordPanel({ email, onEmailChange, onAuthed, onBusyChange }: Props) {
  const id = useId()
  const [password, setPassword] = useState('')
  const [visible, setVisible] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const locked = useRef(false)
  const mounted = useRef(true)
  const valid = isValidEmail(email.trim()) && password.length > 0

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!valid || locked.current) return
    locked.current = true
    setPending(true); onBusyChange(true); setError('')
    try {
      const result = await authService.loginWithPassword(email, password)
      if (mounted.current) { setPassword(''); onAuthed(result) }
    } catch (error) {
      if (mounted.current) setError(error instanceof Error ? error.message : 'Unable to sign in. Please try again.')
    } finally {
      locked.current = false
      if (mounted.current) { setPending(false); onBusyChange(false) }
    }
  }

  return <form className={panel.panel} onSubmit={submit} aria-label="Password sign in" aria-busy={pending}>
    <p className={panel.helperText}>Sign in with the email and password for your existing account.</p>
    <label htmlFor={`${id}-email`} className={panel.label}>Email</label>
    <input id={`${id}-email`} name="email" type="email" autoComplete="username" className={panel.input}
      value={email} required disabled={pending} placeholder="Enter your email address"
      onChange={event => { onEmailChange(event.target.value); setError('') }} />
    <label htmlFor={`${id}-password`} className={panel.label}>Password</label>
    <div className={panel.passwordField}>
      <input id={`${id}-password`} name="password" type={visible ? 'text' : 'password'} autoComplete="current-password"
        className={panel.input} value={password} required disabled={pending} maxLength={128}
        placeholder="Enter your password" aria-describedby={error ? `${id}-error` : undefined}
        onChange={event => { setPassword(event.target.value); setError('') }} />
      <button type="button" className={panel.passwordToggle} disabled={pending} aria-label={visible ? 'Hide password' : 'Show password'}
        aria-pressed={visible} onClick={() => setVisible(value => !value)}>{visible ? 'Hide' : 'Show'}</button>
    </div>
    <div id={`${id}-error`} className={panel.errorText} role="alert">{error}</div>
    <button type="submit" className={panel.primaryBtn} disabled={!valid || pending}>{pending ? 'Signing in…' : 'Sign in with password'}</button>
  </form>
}