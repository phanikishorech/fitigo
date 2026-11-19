import NotificationCenter from '../../components/common/NotificationCenter'
import { Heading, Link } from '../../components/common/UI'

export default function NotificationsPage() {
  return <div className="fg-narrow fg-stack"><Heading title="Notifications" subtitle="Updates about your visits and your FitiGo account." /><NotificationCenter preferences={false} /><Link to="/settings" className="fg-inline-link">Notification email preferences</Link></div>
}