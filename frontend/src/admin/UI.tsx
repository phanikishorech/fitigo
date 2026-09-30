import { createContext, useContext, useEffect, useId, useState, type ReactNode } from 'react'
import { Button, Link, Modal, Image, Skeleton, EmptyState } from '../components/common/UI'
import Icon, { type IconName } from '../components/common/Icon'
import { useMutation } from '../hooks/useResource'
import { adminError } from './services'
export { Button, Link, Modal, Image, Skeleton, EmptyState, Icon }

export const personName = (user: { first_name: string | null; last_name: string | null; id: number }) => [user.first_name, user.last_name].filter(Boolean).join(' ') || `User #${user.id}`
export const readable = (value: string) => value.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, char => char.toUpperCase())
export function StatusBadge({ status }: { status: string }) {
  const tone = /^(ACTIVE|APPROVED|PAID|ATTENDED|REFUNDED|SENT)$/.test(status) ? 'success' : /PENDING|INITIATED/.test(status) ? 'warning' : /REJECTED|FAILED|CANCELLED|NO_SHOW|SUSPENDED|EXPIRED/.test(status) ? 'danger' : status === 'CONFIRMED' ? 'info' : 'neutral'
  return <span className={`ad-badge ad-badge--${tone}`}><span aria-hidden="true">{tone === 'success' ? '✓' : tone === 'danger' ? '×' : '•'}</span>{readable(status)}</span>
}
export function PageHeader({ title, subtitle, action, back }: { title: string; subtitle?: string; action?: ReactNode; back?: { to: string; label: string } }) {
  return <>{back && <nav aria-label="Breadcrumbs" className="ad-breadcrumb"><Link to={back.to}><Icon name="back" size={16} />{back.label}</Link></nav>}<div className="ad-page-header"><div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>{action}</div></>
}
export function DataCard({ title, action, children, className = '' }: { title?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`ad-card ${className}`}>{title && <div className="ad-card-header"><h2>{title}</h2>{action}</div>}<div className="ad-card-body">{children}</div></section>
}
export function MetricCard({ title, value, caption, icon }: { title: string; value: ReactNode; caption: string; icon: IconName }) {
  return <div className="ad-card ad-metric"><div className="ad-metric-heading"><span>{title}</span><span className="ad-icon-tile"><Icon name={icon} /></span></div><strong>{value}</strong><small>{caption}</small></div>
}
export function Alert({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'warning' | 'danger' | 'success' }) { return <div className={`ad-alert ad-alert--${tone}`} role={tone === 'danger' ? 'alert' : 'status'}><Icon name={tone === 'success' ? 'check' : 'shield'} /><div>{children}</div></div> }
export function ErrorState({ message, retry }: { message: string; retry: () => void }) {
  return <EmptyState title={message.startsWith('Access denied') ? 'Access denied' : message.startsWith('Unable to connect') ? 'Unable to connect' : message.includes('could not be found') ? 'Record not found' : 'Unable to load this view'} description={message} action={<Button variant="secondary" onClick={retry}>Try again</Button>} />
}
export function Resource<T>({ resource, children }: { resource: { loading: boolean; error: string; data: T | null; retry: () => void }; children: (data: T) => ReactNode }) {
  if (resource.loading) return <Skeleton cards={2} />
  if (resource.error) return <ErrorState message={resource.error} retry={resource.retry} />
  return <>{resource.data !== null && children(resource.data)}</>
}
export function SearchInput({ value, onChange, placeholder, busy }: { value: string; onChange: (value: string) => void; placeholder: string; busy?: boolean }) {
  return <div className="ad-search"><Icon name="search" /><input type="search" aria-label={placeholder} placeholder={placeholder} maxLength={100} value={value} onChange={e => onChange(e.target.value)} />{busy && <span role="status" className="ad-search-busy">Searching…</span>}{value && <Button variant="text" aria-label="Clear search" onClick={() => onChange('')}><Icon name="close" size={16} /></Button>}</div>
}
export function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: { value: string; label: string }[] }) {
  return <label className="ad-field"><span>{label}</span><select value={value} onChange={e => onChange(e.target.value)}>{options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
}
export function DatePicker({ label, value, onChange, min, max }: { label: string; value: string; onChange: (value: string) => void; min?: string; max?: string }) {
  return <label className="ad-field"><span>{label}</span><input type="date" value={value} min={min} max={max} onChange={e => onChange(e.target.value)} /></label>
}
export function Tabs({ options, value, onChange, label = 'Filter records' }: { options: { value: string; label: string }[]; value: string; onChange: (value: string) => void; label?: string }) {
  return <div className="ad-tabs" role="group" aria-label={label}>{options.map(option => <button key={option.value} type="button" aria-pressed={value === option.value} className={value === option.value ? 'is-active' : ''} onClick={() => onChange(option.value)}>{option.label}</button>)}</div>
}
export function FilterPanel({ children, reset }: { children: ReactNode; reset: () => void }) {
  const [open, setOpen] = useState(false)
  return <><div className="ad-desktop-filters">{children}<Button variant="text" onClick={reset}>Reset</Button></div><Button variant="secondary" className="ad-mobile-filter" onClick={() => setOpen(true)}><Icon name="filter" />Filters</Button>{open && <div className="ad-bottom-sheet"><Modal title="Filter records" onClose={() => setOpen(false)}><div className="ad-filter-fields">{children}</div><div className="ad-dialog-actions"><Button variant="secondary" onClick={reset}>Reset filters</Button><Button onClick={() => setOpen(false)}>Show results</Button></div></Modal></div>}</>
}
export type Column<T> = { label: string; cell: (row: T) => ReactNode }
export function DataTable<T extends { id: number }>({ rows, columns, mobile, label, empty }: { rows: T[]; columns: Column<T>[]; mobile: (row: T) => ReactNode; label: string; empty: string }) {
  if (!rows.length) return <EmptyState title={empty} description="Try another search or adjust your filters." />
  return <><div className="ad-table-wrap"><table className="ad-table"><caption className="srOnly">{label}</caption><thead><tr>{columns.map(column => <th key={column.label} scope="col">{column.label}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.id}>{columns.map(column => <td key={column.label}>{column.cell(row)}</td>)}</tr>)}</tbody></table></div><div className="ad-mobile-records">{rows.map(row => <article className="ad-mobile-card" key={row.id}>{mobile(row)}</article>)}</div></>
}
export function Pagination({ page, count, hasMore, onPage, loading }: { page: number; count: number; hasMore: boolean; onPage: (page: number) => void; loading?: boolean }) {
  return <nav aria-label="Pagination" className="ad-pagination"><span>{count ? `Showing ${(page - 1) * 20 + 1}–${(page - 1) * 20 + count}` : 'No records on this page'}</span><div><Button variant="secondary" disabled={page === 1 || loading} onClick={() => onPage(page - 1)} aria-label="Previous page"><Icon name="back" size={16} /></Button><span aria-current="page">Page {page}</span><Button variant="secondary" disabled={!hasMore || loading} onClick={() => onPage(page + 1)} aria-label="Next page"><Icon name="arrow" size={16} /></Button></div></nav>
}
export function Details({ rows }: { rows: [string, ReactNode][] }) { return <dl className="ad-details">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? 'Not provided'}</dd></div>)}</dl> }
export function Avatar({ name }: { name: string }) { return <span className="ad-avatar" aria-hidden="true">{name.split(' ').map(part => part[0]).slice(0, 2).join('').toUpperCase()}</span> }
export function Identity({ name, caption, icon }: { name: string; caption?: string; icon?: IconName }) { return <div className="ad-identity">{icon ? <span className="ad-icon-tile"><Icon name={icon} /></span> : <Avatar name={name} />}<span><strong>{name}</strong>{caption && <small>{caption}</small>}</span></div> }
export function ImageGallery({ images, name }: { images: { src: string; alt: string }[]; name: string }) {
  const [preview, setPreview] = useState<number | null>(null)
  return <>{images.length ? <div className="ad-gallery">{images.map((image, i) => <button type="button" key={image.src} onClick={() => setPreview(i)} aria-label={`Preview ${image.alt}`}><Image src={image.src} alt={image.alt} /></button>)}</div> : <div className="ad-gallery-empty"><Icon name="gym" size={40} /><p>No photos available for {name}.</p></div>}{preview !== null && <Modal title={images[preview].alt} onClose={() => setPreview(null)}><Image src={images[preview].src} alt={images[preview].alt} className="ad-preview-image" /><div className="ad-dialog-actions"><Button variant="secondary" disabled={preview === 0} onClick={() => setPreview(preview - 1)}>Previous</Button><Button variant="secondary" disabled={preview === images.length - 1} onClick={() => setPreview(preview + 1)}>Next</Button></div></Modal>}</>
}
const ToastContext = createContext<(message: string, tone?: 'success' | 'warning') => void>(() => {})
export const useToast = () => useContext(ToastContext)
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ message: string; tone: 'success' | 'warning' } | null>(null)
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(null), 6500); return () => clearTimeout(timer) }, [toast])
  return <ToastContext.Provider value={(message, tone = 'success') => setToast({ message, tone })}>{children}<div className="ad-toast-region" aria-live="polite" aria-atomic="true">{toast && <div className={`ad-toast ad-toast--${toast.tone}`}><Icon name="check" /><span>{toast.message}</span><Button variant="text" aria-label="Dismiss notification" onClick={() => setToast(null)}><Icon name="close" /></Button></div>}</div></ToastContext.Provider>
}
export function ConfirmationModal({ title, children, confirm, danger, reason, onClose, action, success, onSuccess }: { title: string; children: ReactNode; confirm: string; danger?: boolean; reason?: 'required' | 'optional'; onClose: () => void; action: (reason: string) => Promise<unknown>; success: string; onSuccess: () => void }) {
  const mutation = useMutation(); const toast = useToast(); const [text, setText] = useState(''); const id = useId()
  return <Modal title={title} onClose={() => { if (!mutation.pending) onClose() }}><form onSubmit={e => { e.preventDefault(); if (reason === 'required' && text.trim().length < 3) { mutation.setError('Enter a reason of at least 3 characters.'); return } void mutation.run(async () => { try { await action(text.trim()) } catch (error) { throw new Error(adminError(error)) } toast(success); onSuccess(); onClose() }) }}><div className="ad-confirm-copy">{children}</div>{reason && <label className="ad-field"><span>Reason {reason === 'optional' ? '(optional)' : ''}</span><textarea value={text} onChange={e => setText(e.target.value)} required={reason === 'required'} minLength={reason === 'required' ? 3 : undefined} maxLength={500} rows={4} aria-describedby={mutation.error ? id : undefined} /><small>{text.length}/500 characters</small></label>}{mutation.error && <div id={id}><Alert tone="danger">{mutation.error}</Alert></div>}<div className="ad-dialog-actions"><Button variant="secondary" disabled={mutation.pending} onClick={onClose}>Keep unchanged</Button><Button type="submit" variant={danger ? 'danger' : 'primary'} loading={mutation.pending}>{confirm}</Button></div></form></Modal>
}