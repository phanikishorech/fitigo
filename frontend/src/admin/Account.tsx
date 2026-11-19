import NotificationCenter from '../components/common/NotificationCenter'
import type { User } from '../services/accountService'
import AccountProfileEditor from '../components/common/AccountProfileEditor'
import ChangePassword from '../owner/ChangePassword'
import { DataCard, Details, EmptyState, Identity, Link, PageHeader, personName, readable } from './UI'

export default function Account({ page, user, roles }: { page: string; user: User; roles: string[] }) {
  if (page === 'notifications') return <NotificationCenter />
  if (page === 'profile') return <><PageHeader title="Admin profile" subtitle="Your verified administrator identity" /><DataCard><Identity name={personName(user)} caption={roles.map(readable).join(' · ')} /><Details rows={[["Name", personName(user)], ['Email', user.email], ['Phone', user.phone], ['User ID', `#${user.id}`], ['Roles', roles.map(readable).join(', ')]]} /><AccountProfileEditor user={user} /><ChangePassword /><NotificationCenter inbox={false} /></DataCard></>
  return <EmptyState title="404 · Page not found" description="This page may have moved, or the address may be incorrect." action={<Link className="fg-button fg-button--primary" to="/admin/dashboard">Back to Dashboard</Link>} />
}
