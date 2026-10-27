import { useState } from 'react'
import { useMutation, useResource } from '../../hooks/useResource'
import { profileService, type User } from '../../services/accountService'
import { Alert, Button, ErrorState, Heading, Link, Skeleton } from '../../components/common/UI'
import { NewPasswordForm } from '../../components/AuthModal/PasswordRecovery'
import { clearTokens } from '../../auth'
import { navigate } from '../../router'

function signInAgain() { navigate('/login', true); clearTokens() }
function ProfileForm({ user }: { user: User }) {
  const mutation = useMutation()
  const [success, setSuccess] = useState(false)
  return <form className="fg-stack" onSubmit={event => {
    event.preventDefault(); const form = event.currentTarget; const values = new FormData(form)
    void mutation.run(async () => {
      const result = await profileService.update({ first_name: String(values.get('first_name')).trim(), last_name: String(values.get('last_name')).trim(), email: String(values.get('email')).trim(), phone: String(values.get('phone')).trim() || null, ...(values.get('current_password') ? { current_password: String(values.get('current_password')) } : {}) })
      if (result.reauthenticate) signInAgain()
      else { setSuccess(true) }
    })
  }}><h2>Edit profile</h2><label className="fg-field">First name<input name="first_name" defaultValue={user.first_name || ''} required maxLength={100} autoComplete="given-name" /></label><label className="fg-field">Last name<input name="last_name" defaultValue={user.last_name || ''} maxLength={100} autoComplete="family-name" /></label><label className="fg-field">Email<input name="email" type="email" defaultValue={user.email} required autoComplete="email" /></label><small>{user.is_email_verified ? 'Email verified' : 'Email not verified'}</small><label className="fg-field">Phone number<input name="phone" type="tel" defaultValue={user.phone || ''} maxLength={16} placeholder="+919876543210" autoComplete="tel" pattern="\+?[1-9][0-9]{7,14}" /></label><small>{user.is_phone_verified ? 'Phone verified' : 'Phone not verified'}</small><label className="fg-field">Current password (required to change email or phone)<input name="current_password" type="password" autoComplete="current-password" maxLength={128} /></label><p className="fg-muted">Changing email or phone signs you out on all devices and marks the changed contact as unverified. This app's contact OTP delivery is not configured; saving does not prove ownership. If you signed up only with OTP, use password recovery first.</p>{mutation.error && <Alert>{mutation.error}</Alert>}{success && <p role="status">Profile saved.</p>}<Button type="submit" loading={mutation.pending}>Save profile</Button></form>
}
export default function SettingsPage() {
  const resource = useResource(profileService.me, 'profile-settings')
  return <div className="fg-narrow fg-stack"><Heading title="Account settings" subtitle="Manage your profile and account security." /><section className="fg-panel">{resource.loading ? <Skeleton cards={1} /> : resource.error ? <ErrorState message={resource.error} retry={resource.retry} /> : resource.data && <ProfileForm user={resource.data} />}</section><section className="fg-panel fg-stack"><h2>Change password</h2><NewPasswordForm change onSuccess={signInAgain} /><Link to="/auth/forgot-password">Forgot your current password?</Link></section><section className="fg-panel fg-stack"><Link to="/profile/payments">Payment history</Link><Link to="/location">Change workout location</Link><Link to="/profile">Back to profile</Link><p className="fg-muted">FitiGo follows your device's reduced-motion preference and supports keyboard navigation.</p></section></div>
}