import { useEffect, useState } from 'react'
import { authService } from '../../services/authService'
import { useMutation, useResource } from '../../hooks/useResource'
import { Alert, Button, ErrorState, Heading, Link, Skeleton } from '../../components/common/UI'

export default function StaffInvitationPage() {
  const [token, setToken] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') || '')
  const [done, setDone] = useState(false)
  const mutation = useMutation()
  const result = useResource(() => token ? authService.inspectInvitation(token) : Promise.reject(new Error('This invitation link is missing. Ask the gym owner to resend it.')), token)
  useEffect(() => {
    // Never keep capability tokens in URL history, storage, analytics or links.
    const capture = () => {
      if (!window.location.hash) return
      setToken(new URLSearchParams(window.location.hash.slice(1)).get('token') || '')
      setDone(false)
      window.history.replaceState(window.history.state, '', window.location.pathname)
    }
    capture(); window.addEventListener('hashchange', capture)
    return () => window.removeEventListener('hashchange', capture)
  }, [])
  return <div className="fg-narrow fg-stack"><Heading title="Accept staff invitation" subtitle="Your gym access is assigned securely by FitiGo." /><section className="fg-panel fg-stack">
    {done ? <p role="status">Invitation accepted. Sign in to access your assigned gyms.</p> : result.loading ? <Skeleton cards={1} /> : result.error ? <ErrorState message={result.error} retry={result.retry} /> : result.data && <>
      <p>You are invited to join <strong>{result.data.gym_name}</strong> as gym staff. This link expires {new Date(result.data.expires_at).toLocaleString()}.</p>
      <form className="fg-stack" aria-label="Accept staff invitation" onSubmit={event => {
        event.preventDefault(); const form = new FormData(event.currentTarget)
        void mutation.run(async () => {
          const password = String(form.get('password'))
          if (!result.data!.requires_current_password && password !== form.get('confirmation')) throw new Error('The passwords do not match.')
          await authService.acceptInvitation(token, password, result.data!.requires_current_password)
          setDone(true)
        })
      }}>
        <p>{result.data.requires_current_password ? 'Confirm your existing account password. Your password and other gym access will not be changed.' : 'Choose your own password. No access is granted until you accept.'}</p>
        <label className="fg-field">{result.data.requires_current_password ? 'Current password' : 'New password'}<input name="password" type="password" autoComplete={result.data.requires_current_password ? 'current-password' : 'new-password'} required minLength={result.data.requires_current_password ? 1 : 8} maxLength={128} disabled={mutation.pending} /></label>
        {!result.data.requires_current_password && <label className="fg-field">Confirm password<input name="confirmation" type="password" autoComplete="new-password" required minLength={8} maxLength={128} disabled={mutation.pending} /></label>}
        {mutation.error && <Alert>{mutation.error}</Alert>}
        <Button type="submit" disabled={mutation.pending}>{mutation.pending ? 'Accepting…' : 'Accept invitation'}</Button>
      </form>
    </>}
    <p>Expired or revoked link? Ask the gym owner to resend your invitation. Reopening the email restores the link if you reload this page.</p>
    <Link to="/owner/login" className="fg-inline-link">Staff sign in</Link><Link to="/auth/forgot-password" className="fg-inline-link">Forgot your existing password?</Link>
  </section></div>
}