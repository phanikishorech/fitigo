import { useState } from 'react'
import { setTokens } from '../auth'
import { ApiError } from '../services/client'
import { navigate } from '../router'
import { adminAuthService, adminError } from './services'
import { adminReturnTo } from './routes'
import { useMutation } from '../hooks/useResource'
import { Alert, Button, Icon, Link } from './UI'

export default function Login() {
  const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const [visible, setVisible] = useState(false); const mutation = useMutation()
  return <div className="ad-login"><section className="ad-login-visual"><div className="ad-login-brand"><span className="fg-logo-mark"><Icon name="gym" size={25} /></span>FitiGo <small>ADMIN PORTAL</small></div><div className="ad-login-copy"><span className="ad-eyebrow">ONE PLATFORM. EVERY POSSIBILITY.</span><h1>A stronger platform.<br />Starts with you.</h1><p>Manage users, gyms and bookings across FitiGo.</p><div className="ad-login-trust"><Icon name="shield" />Your platform. A secure workspace.</div></div><small>Built for the people behind the movement.</small></section><section className="ad-login-form"><div><span className="ad-icon-tile"><Icon name="shield" size={25} /></span><span className="ad-eyebrow">FITIGO ADMIN</span><h2>Welcome back</h2><p>Sign in to your admin account.</p><form onSubmit={e => { e.preventDefault(); void mutation.run(async () => {
    try {
      const tokens = await adminAuthService.login(email, password); setTokens(tokens.access_token, tokens.refresh_token)
      await adminAuthService.identity()
      navigate(adminReturnTo(new URLSearchParams(window.location.search).get('returnTo')))
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) { navigate('/admin/access-denied'); return }
      throw new Error(error instanceof ApiError && error.status === 401 ? 'Incorrect email or password.' : adminError(error))
    }
  }) }}><label className="ad-field"><span>Email address</span><input name="email" type="email" autoComplete="username" required maxLength={255} placeholder="you@fitigo.com" value={email} onChange={e => setEmail(e.target.value)} aria-describedby={mutation.error ? 'login-error' : undefined} /></label><label className="ad-field"><span>Password</span><div className="ad-password"><input name="password" type={visible ? 'text' : 'password'} autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} aria-describedby={mutation.error ? 'login-error' : undefined} /><Button variant="text" aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible} onClick={() => setVisible(!visible)}>{visible ? 'Hide' : 'Show'}</Button></div></label>{mutation.error && <div id="login-error"><Alert tone="danger">{mutation.error}</Alert></div>}<Button type="submit" disabled={mutation.pending} aria-busy={mutation.pending}>{mutation.pending ? 'Signing in…' : 'Sign In'}<Icon name="arrow" size={18} /></Button></form><p className="ad-login-help">Restricted to authorized administrators.<br />Contact your platform administrator if you need access.</p><Link to="/home" className="ad-back-home"><Icon name="back" size={16} />Back to FitiGo</Link></div></section></div>
}