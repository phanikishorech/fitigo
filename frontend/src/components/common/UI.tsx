import { useEffect, useId, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { navigate } from '../../router'
import Icon from './Icon'

export function Button({ children, variant = 'primary', loading, className = '', disabled, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'text' | 'danger'; loading?: boolean }) {
  return <button type="button" {...props} disabled={disabled || loading} aria-busy={loading || undefined} className={`fg-button fg-button--${variant} ${className}`}>{loading ? 'Please wait…' : children}</button>
}
export function Link({ to, children, className = '', label }: { to: string; children: ReactNode; className?: string; label?: string }) {
  return <a href={to} className={className} aria-label={label} onClick={e => { if (!e.ctrlKey && !e.metaKey && !e.shiftKey && !e.altKey && e.button === 0) { e.preventDefault(); navigate(to) } }}>{children}</a>
}
export function Heading({ eyebrow, title, subtitle, action }: { eyebrow?: string; title: string; subtitle?: string; action?: ReactNode }) {
  return <div className="fg-heading"><div>{eyebrow && <span className="fg-eyebrow">{eyebrow}</span>}<h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>{action}</div>
}
export function Alert({ children }: { children: ReactNode }) { return <div className="fg-alert" role="alert">{children}</div> }
export function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="fg-empty"><span className="fg-empty-icon"><Icon name="gym" size={32} /></span><h2>{title}</h2>{description && <p>{description}</p>}{action}</div>
}
export function ErrorState({ message, retry }: { message: string; retry: () => void }) { return <EmptyState title="Something went wrong" description={message} action={<Button variant="secondary" onClick={retry}>Try again</Button>} /> }
export function Skeleton({ cards = 3 }: { cards?: number }) {
  return <div className="fg-skeleton-grid" role="status" aria-label="Loading"><span className="srOnly">Loading…</span>{Array.from({ length: cards }, (_, i) => <div className="fg-skeleton-card" key={i}><div /><span /><span /></div>)}</div>
}
export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'success' | 'warning' }) { return <span className={`fg-badge fg-badge--${tone}`}>{children}</span> }
export function Image({ src, alt, className = '' }: { src?: string | null; alt: string; className?: string }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [src])
  const safeSrc = src && (/^\/(?!\/)/.test(src) || /^https?:\/\//i.test(src)) ? src : null
  return safeSrc && !failed ? <img src={safeSrc} alt={alt} className={className} loading="lazy" decoding="async" onError={() => setFailed(true)} /> : <div className={`fg-image-fallback ${className}`} role="img" aria-label={`${alt} — photo unavailable`}><Icon name="gym" size={42} /><span>FitiGo partner gym</span></div>
}
export function Modal({ title, children, onClose, showCloseButton = true, className = '', describedBy }: { title: string; children: ReactNode; onClose: () => void; showCloseButton?: boolean; className?: string; describedBy?: string }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const id = useId()
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'; dialog.current?.showModal()
    return () => { document.body.style.overflow = overflow; previous?.focus() }
  }, [])
  return <dialog ref={dialog} className={`fg-dialog ${className}`} aria-labelledby={id} aria-describedby={describedBy} onCancel={e => { e.preventDefault(); onClose() }} onClick={e => { if (e.target === dialog.current) onClose() }}><div className="fg-dialog-inner"><div className="fg-section-heading"><h2 id={id}>{title}</h2>{showCloseButton && <Button variant="text" aria-label="Close dialog" onClick={onClose}><Icon name="close" /></Button>}</div>{children}</div></dialog>
}