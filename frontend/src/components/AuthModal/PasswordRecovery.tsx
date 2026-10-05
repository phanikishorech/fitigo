import { useId, useState } from 'react'
import { useMutation, useResource } from '../../hooks/useResource'
import { authService } from '../../services/authService'
import panel from './panel.module.css'

export function ForgotPassword({ onBusyChange }: { onBusyChange?: (busy: boolean) => void }) {
  const options = useResource(authService.resetOptions, 'password-reset-options')
  const mutation = useMutation(); const [sent, setSent] = useState(false); const id = useId()
  if (options.loading) return <p role="status" className={panel.helperText}>Checking password recovery…</p>
  if (options.error) return <div className={panel.panel}><p role="alert" className={panel.errorText}>Unable to check password recovery.</p><button className={panel.secondaryLink} onClick={options.retry}>Try Again</button></div>
  if (!options.data?.email_available) return <p role="status" className={panel.helperText}>Password reset email is not available yet. Contact your FitiGo administrator to configure email delivery. No reset link has been sent.</p>
  if (sent) return <div className={panel.panel}><p role="status" className={panel.helperText}>If an active account exists for this email, you will receive a password reset link. Check your inbox and spam folder. The link expires in 30 minutes.</p><button className={panel.secondaryLink} onClick={() => setSent(false)}>Request another link</button></div>
  return <form className={panel.panel} aria-label="Forgot password" onSubmit={event => {
    event.preventDefault(); const email = String(new FormData(event.currentTarget).get('email'))
    void mutation.run(async () => { onBusyChange?.(true); try { await authService.forgotPassword(email); setSent(true) } finally { onBusyChange?.(false) } })
  }}>
    <p className={panel.helperText}>Enter your account email. We’ll send a link to choose a new password.</p>
    <label className={panel.label} htmlFor={`${id}-email`}>Email</label><input id={`${id}-email`} className={panel.input} name="email" type="email" autoComplete="email" required disabled={mutation.pending} />
    {mutation.error && <p className={panel.errorText} role="alert">{mutation.error}</p>}
    <button className={panel.primaryBtn} disabled={mutation.pending}>{mutation.pending ? 'Requesting link…' : 'Send reset link'}</button>
  </form>
}

export function NewPasswordForm({ token, change = false, onSuccess }: { token?: string; change?: boolean; onSuccess: () => void }) {
  const mutation = useMutation(); const id = useId(); const [visible, setVisible] = useState(false)
  return <form className={panel.panel} aria-label={change ? 'Change password' : 'Reset password'} aria-busy={mutation.pending} onSubmit={event => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form)
    void mutation.run(async () => {
      const password = String(data.get('new_password'))
      if (password !== data.get('confirmation')) throw new Error('The passwords do not match.')
      if (change) await authService.changePassword(String(data.get('current_password')), password)
      else if (token) await authService.resetPassword(token, password)
      else throw new Error('This reset link is invalid. Request a new link.')
      form.reset(); onSuccess()
    })
  }}>
    <p className={panel.helperText}>Use at least 8 characters. After changing your password, sign in again on your devices.</p>
    {change && <><label className={panel.label} htmlFor={`${id}-current`}>Current password</label><input id={`${id}-current`} className={panel.input} name="current_password" type={visible ? 'text' : 'password'} autoComplete="current-password" required maxLength={128} disabled={mutation.pending} /></>}
    <label className={panel.label} htmlFor={`${id}-new`}>New password</label><input id={`${id}-new`} className={panel.input} name="new_password" type={visible ? 'text' : 'password'} autoComplete="new-password" required minLength={8} maxLength={128} disabled={mutation.pending} aria-describedby={mutation.error ? `${id}-error` : undefined} />
    <label className={panel.label} htmlFor={`${id}-confirm`}>Confirm new password</label><input id={`${id}-confirm`} className={panel.input} name="confirmation" type={visible ? 'text' : 'password'} autoComplete="new-password" required minLength={8} maxLength={128} disabled={mutation.pending} />
    <button type="button" className={panel.secondaryLink} aria-pressed={visible} onClick={() => setVisible(v => !v)} disabled={mutation.pending}>{visible ? 'Hide passwords' : 'Show passwords'}</button>
    {mutation.error && <p id={`${id}-error`} className={panel.errorText} role="alert">{mutation.error}</p>}
    <button className={panel.primaryBtn} disabled={mutation.pending}>{mutation.pending ? 'Updating password…' : change ? 'Change password' : 'Reset password'}</button>
  </form>
}