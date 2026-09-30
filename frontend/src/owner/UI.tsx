import { useId, type ReactNode, type InputHTMLAttributes } from 'react'
import { Button, EmptyState, ErrorState, Link, Modal, Skeleton } from '../components/common/UI'
import Icon, { type IconName } from '../components/common/Icon'
export { Button, EmptyState, ErrorState, Link, Modal, Skeleton }

export function PageHeader({ title, description, action, eyebrow }: { title: string; description?: string; action?: ReactNode; eyebrow?: string }) {
  return <header className="ow-page-header"><div>{eyebrow && <span className="ow-eyebrow">{eyebrow}</span>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</header>
}
export function Card({ title, action, children, className = '' }: { title?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`ow-card ${className}`}>{title && <div className="ow-card-heading"><h2>{title}</h2>{action}</div>}{children}</section>
}
export function StatusBadge({ status }: { status: string }) {
  const positive = ['ACTIVE', 'APPROVED', 'ATTENDED', 'PAID', 'SUCCESS', 'CHECKED_IN'].includes(status)
  const negative = ['REJECTED', 'FAILED', 'NO_SHOW', 'EXPIRED', 'ACCESS_DENIED'].includes(status)
  const warning = ['PENDING_APPROVAL', 'PENDING_PAYMENT', 'PENDING'].includes(status)
  return <span className={`ow-badge ow-badge--${positive ? 'success' : negative ? 'danger' : warning ? 'warning' : status === 'CONFIRMED' ? 'info' : 'neutral'}`}><Icon name={positive ? 'check' : negative ? 'close' : warning ? 'clock' : 'ticket'} size={13} />{status.replace(/_/g, ' ').toLowerCase()}</span>
}
export function MetricCard({ icon, label, value, note }: { icon: IconName; label: string; value: ReactNode; note: string }) {
  return <section className="ow-card ow-metric"><div className="ow-metric-top"><span>{label}</span><span className="ow-icon-tile"><Icon name={icon} /></span></div><strong>{value}</strong><p>{note}</p></section>
}
export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label className="ow-field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>
}
export function Input({ label, hint, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  const id = useId()
  return <Field label={label} hint={hint}><input id={id} {...props} /></Field>
}
export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'success' | 'error' }) {
  return <div className={`ow-notice ow-notice--${tone}`} role={tone === 'error' ? 'alert' : 'status'}><Icon name={tone === 'success' ? 'check' : 'shield'} size={18} /><div>{children}</div></div>
}
export function Unavailable({ title, message }: { title: string; message: string }) {
  return <div className="ow-unavailable"><span className="ow-icon-tile"><Icon name="shield" /></span><h3>{title}</h3><p>{message}</p></div>
}
export function Pagination({ page, hasMore, onChange }: { page: number; hasMore: boolean; onChange: (page: number) => void }) {
  return <nav className="ow-pagination" aria-label="Pagination"><Button variant="secondary" disabled={page === 0} onClick={() => onChange(page - 1)}>Previous</Button><span>Page {page + 1}</span><Button variant="secondary" disabled={!hasMore} onClick={() => onChange(page + 1)}>Next</Button></nav>
}
export function ConfirmDialog({ title, children, label, pending, error, onConfirm, onClose, destructive }: { title: string; children: ReactNode; label: string; pending: boolean; error?: string; onConfirm: () => void; onClose: () => void; destructive?: boolean }) {
  return <Modal title={title} onClose={() => { if (!pending) onClose() }}><div className="ow-stack"><div className="ow-stack">{children}</div>{error && <Notice tone="error">{error}</Notice>}<div className="ow-actions"><Button variant="secondary" disabled={pending} onClick={onClose}>Keep unchanged</Button><Button variant={destructive ? 'danger' : 'primary'} loading={pending} onClick={onConfirm}>{label}</Button></div></div></Modal>
}
export function Breadcrumbs({ items }: { items: { label: string; to?: string }[] }) {
  return <nav aria-label="Breadcrumb" className="ow-breadcrumbs">{items.map((item, i) => <span key={i}>{i > 0 && <Icon name="chevron" size={14} />}{item.to ? <Link to={item.to}>{item.label}</Link> : <span aria-current="page">{item.label}</span>}</span>)}</nav>
}