import { useEffect, useState } from 'react'
import { authService } from '../services/authService'
import { ownerService } from './services'
import { setTokens } from '../auth'
import { navigate } from '../router'
import { useMutation } from '../hooks/useResource'
import { Button, Input, Link, Notice } from './UI'
import Icon from '../components/common/Icon'

export default function AuthPage({ page }: { page: string }) {
  const mutation = useMutation()
  const [email, setEmail] = useState(() => { try { return sessionStorage.getItem('fitigo:owner:verify-email') || '' } catch { return '' } })
  const [otp, setOtp] = useState('')
  const [sent, setSent] = useState(false)
  const [remaining, setRemaining] = useState(0)
  const [visible, setVisible] = useState(false)
  useEffect(() => { if (remaining > 0) { const timer = setTimeout(() => setRemaining(n => n - 1), 1000); return () => clearTimeout(timer) } }, [remaining])
  const register = page === 'register'; const verify = page === 'verify'
  async function send() { await authService.sendEmail(email.trim().toLowerCase()); setSent(true); setRemaining(30) }
  return <div className="ow-auth"><div className="ow-auth-brand"><Link to="/owner/login" className="fg-logo"><span className="fg-logo-mark"><Icon name="gym" /></span>Fiti<span>Go</span></Link><span className="ow-eyebrow">OWNER PORTAL</span></div><main className="ow-auth-card"><span className="ow-icon-tile"><Icon name={verify ? 'shield' : 'gym'} size={26} /></span><h1>{register ? 'Create your owner account' : verify ? 'Verify your account' : 'Welcome back'}</h1><p>{register ? 'A better way to run your gym starts here.' : verify ? 'Verify your email using a one-time code.' : 'Manage your gym, bookings and members from one place.'}</p>
    <form className="ow-stack" onSubmit={e => { e.preventDefault(); const form = new FormData(e.currentTarget); void mutation.run(async () => {
      if (register) { const address = String(form.get('email')).trim().toLowerCase(); await ownerService.register({ first_name: String(form.get('first_name')).trim(), last_name: String(form.get('last_name')).trim(), email: address, phone: String(form.get('phone')).trim() || null, password: String(form.get('password')) }); try { sessionStorage.setItem('fitigo:owner:verify-email', address) } catch { /* email can be re-entered */ } navigate('/owner/verify'); return }
      if (verify && !sent) { await send(); return }
      const tokens = verify ? await authService.verifyEmail(email.trim().toLowerCase(), otp) : await authService.loginWithPassword(String(form.get('email')), String(form.get('password')))
      setTokens(tokens.access_token, tokens.refresh_token); try { sessionStorage.removeItem('fitigo:owner:verify-email') } catch { /* optional persistence */ } navigate('/owner/dashboard')
    }) }}>
      {register && <div className="ow-form-grid"><Input label="First name" name="first_name" autoComplete="given-name" required maxLength={100} /><Input label="Last name" name="last_name" autoComplete="family-name" required maxLength={100} /></div>}
      <Input label="Email address" name="email" type="email" autoComplete="email" required value={email} disabled={verify && sent} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
      {register && <Input label="Mobile number (optional)" name="phone" type="tel" autoComplete="tel" maxLength={30} />}
      {!verify && <div className="ow-password"><Input label="Password" name="password" type={visible ? 'text' : 'password'} autoComplete={register ? 'new-password' : 'current-password'} minLength={register ? 8 : 1} maxLength={128} required hint={register ? 'At least 8 characters.' : undefined} /><button type="button" onClick={() => setVisible(v => !v)} aria-label={visible ? 'Hide password' : 'Show password'}>{visible ? 'Hide' : 'Show'}</button></div>}
      {verify && sent && <><Notice tone="success">Code requested for {email}. Check your email.</Notice><Input label="Verification code" value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))} pattern="[0-9]{6}" maxLength={6} inputMode="numeric" autoComplete="one-time-code" required /><Button variant="text" disabled={remaining > 0 || mutation.pending} onClick={() => void mutation.run(send)}>{remaining ? `Resend in ${remaining}s` : 'Resend code'}</Button></>}
      {mutation.error && <Notice tone="error">{mutation.error}</Notice>}
      <Button type="submit" loading={mutation.pending}>{register ? 'Create account' : verify ? sent ? 'Verify account' : 'Send verification code' : 'Sign in'}<Icon name="arrow" size={18} /></Button>
    </form><div className="ow-auth-footer">{register || verify ? <Link to="/owner/login">Already have an account? Sign in</Link> : <>New to FitiGo? <Link to="/owner/register">Create owner account</Link></>}</div>
  </main><p className="ow-auth-bottom"><Icon name="shield" size={15} /> Your gym. Your community. One workspace.</p></div>
}