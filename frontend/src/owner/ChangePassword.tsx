import { useState } from 'react'
import { NewPasswordForm } from '../components/AuthModal/PasswordRecovery'
import { Button, Card } from './UI'
import { clearTokens } from '../auth'
import { navigate } from '../router'

export default function ChangePassword() {
  const [open, setOpen] = useState(false)
  return <Card title="Password"><p className="ow-muted">Update the password for your account. This signs you out on all devices.</p>{open ? <NewPasswordForm change onSuccess={() => { navigate('/login?passwordChanged=1', true); clearTokens() }} /> : <Button variant="secondary" onClick={() => setOpen(true)}>Change password</Button>}</Card>
}