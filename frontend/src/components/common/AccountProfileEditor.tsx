import { useState } from 'react'
import { profileService, type User } from '../../services/accountService'
import { useMutation } from '../../hooks/useResource'
import { restoreSession } from '../../session/store'
import { clearTokens } from '../../auth'
import { navigate } from '../../router'
import { Button, Alert } from './UI'

export default function AccountProfileEditor({ user }: { user: User }) {
  const mutation = useMutation()
  const [saved, setSaved] = useState(false)
  return <form className="ow-stack" onChange={() => setSaved(false)} onSubmit={event => {
    event.preventDefault(); const data = new FormData(event.currentTarget)
    void mutation.run(async () => {
      const result = await profileService.update({ first_name: String(data.get('first_name')), last_name: String(data.get('last_name')),
        email: String(data.get('email')), phone: String(data.get('phone')).trim() || null,
        current_password: String(data.get('current_password')) || undefined })
      if (result.reauthenticate) { navigate('/login?profileChanged=1', true); clearTokens(); return }
      setSaved(true); await restoreSession()
    })
  }}>
    <div className="ow-form-grid">{(['first_name', 'last_name', 'email', 'phone'] as const).map(field => <label className="ow-field" key={field}>
      <span>{({ first_name: 'First name', last_name: 'Last name', email: 'Email', phone: 'Phone' })[field]}</span>
      <input name={field} defaultValue={user[field] || ''} type={field === 'email' ? 'email' : field === 'phone' ? 'tel' : 'text'}
        required={field === 'first_name' || field === 'email'} maxLength={field === 'email' ? 255 : field === 'phone' ? 16 : 100} disabled={mutation.pending} />
    </label>)}</div>
    <label className="ow-field"><span>Current password (required to change email or phone)</span><input name="current_password" type="password" autoComplete="current-password" maxLength={128} disabled={mutation.pending} /></label>
    <p>Changing contact details clears their verification and signs you out on all devices. Password and recovery rules are unchanged.</p>
    {mutation.error && <Alert>{mutation.error}</Alert>}{saved && <p role="status">Profile saved.</p>}
    <Button type="submit" loading={mutation.pending}>Save profile</Button>
  </form>
}