import { useId } from 'react'
import { useMutation } from '../../hooks/useResource'
import { authService } from '../../services/authService'
import panel from './panel.module.css'

export default function RegisterPanel({ email, onEmailChange, onRegistered, onBusyChange }: { email: string; onEmailChange: (value: string) => void; onRegistered: () => void; onBusyChange: (busy: boolean) => void }) {
  const mutation = useMutation(); const id = useId()
  return <form className={panel.panel} aria-label="Create customer account" aria-busy={mutation.pending} onSubmit={event => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form)
    void mutation.run(async () => {
      const password = String(data.get('password'))
      if (password !== data.get('confirmation')) throw new Error('The passwords do not match.')
      if (!String(data.get('first_name')).trim() || !String(data.get('last_name')).trim()) throw new Error('Enter your first and last name.')
      onBusyChange(true)
      try {
        await authService.registerCustomer({ first_name: String(data.get('first_name')).trim(), last_name: String(data.get('last_name')).trim(), email, phone: String(data.get('phone')).trim() || null, password })
        form.reset(); onRegistered()
      } finally { onBusyChange(false) }
    })
  }}>
    <p className={panel.helperText}>Create your FitiGo customer account to book visits and manage memberships.</p>
    <label className={panel.label} htmlFor={`${id}-first`}>First name</label><input id={`${id}-first`} className={panel.input} name="first_name" autoComplete="given-name" required maxLength={100} disabled={mutation.pending} />
    <label className={panel.label} htmlFor={`${id}-last`}>Last name</label><input id={`${id}-last`} className={panel.input} name="last_name" autoComplete="family-name" required maxLength={100} disabled={mutation.pending} />
    <label className={panel.label} htmlFor={`${id}-email`}>Email</label><input id={`${id}-email`} className={panel.input} name="email" type="email" autoComplete="email" value={email} onChange={e => onEmailChange(e.target.value)} required disabled={mutation.pending} />
    <label className={panel.label} htmlFor={`${id}-phone`}>Phone (optional)</label><input id={`${id}-phone`} className={panel.input} name="phone" type="tel" autoComplete="tel" maxLength={30} disabled={mutation.pending} />
    <label className={panel.label} htmlFor={`${id}-password`}>Password</label><input id={`${id}-password`} className={panel.input} name="password" type="password" autoComplete="new-password" minLength={8} maxLength={128} required disabled={mutation.pending} aria-describedby={`${id}-hint`} />
    <p id={`${id}-hint`} className={panel.helperText}>Use at least 8 characters.</p>
    <label className={panel.label} htmlFor={`${id}-confirmation`}>Confirm password</label><input id={`${id}-confirmation`} className={panel.input} name="confirmation" type="password" autoComplete="new-password" minLength={8} maxLength={128} required disabled={mutation.pending} />
    {mutation.error && <p className={panel.errorText} role="alert">{mutation.error}</p>}
    <button className={panel.primaryBtn} disabled={mutation.pending}>{mutation.pending ? 'Creating account…' : 'Create account'}</button>
  </form>
}