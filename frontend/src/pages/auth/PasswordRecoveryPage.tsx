import { useEffect, useState } from 'react'
import { ForgotPassword, NewPasswordForm } from '../../components/AuthModal/PasswordRecovery'
import { Heading, Link } from '../../components/common/UI'
import { clearTokens } from '../../auth'

export default function PasswordRecoveryPage({ reset }: { reset: boolean }) {
  const [token, setToken] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') || '')
  const [success, setSuccess] = useState(false)
  useEffect(() => {
    const capture = () => {
      if (!reset || !window.location.hash) return
      setToken(new URLSearchParams(window.location.hash.slice(1)).get('token') || '')
      window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search)
      setSuccess(false)
    }
    capture(); window.addEventListener('hashchange', capture)
    return () => window.removeEventListener('hashchange', capture)
  }, [reset])
  return <div className="fg-narrow"><Heading title={success ? 'Password updated' : reset ? 'Reset password' : 'Forgot password'} subtitle="Secure access to your FitiGo account." /><section className="fg-panel fg-stack">
    {success ? <p role="status">Your password has been updated. Sign in using your new password.</p> : reset ? token ? <NewPasswordForm token={token} onSuccess={() => { setToken(''); clearTokens(); setSuccess(true) }} /> : <p role="alert">This reset link is missing or invalid. Request a new link.</p> : <ForgotPassword />}
    {reset && !success && <Link to="/auth/forgot-password" className="fg-inline-link">Request a new reset link</Link>}
    <Link to="/auth/login" className="fg-button fg-button--secondary">Customer sign in</Link>
    <Link to="/owner/login" className="fg-inline-link">Gym owner / staff sign in</Link>
  </section></div>
}