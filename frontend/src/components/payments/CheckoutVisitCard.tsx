import { dateLabel, money } from '../../services/client'
import Icon from '../common/Icon'

export type CheckoutVisit = { id: number; name: string; date: string; start?: string | null; end?: string | null; quantity: number; amount: string; currency: string; label?: string }

export default function CheckoutVisitCard({ visit, index }: { visit: CheckoutVisit; index: number }) {
  return <article className="fc-visit">
    <div className="fc-visit-icon"><Icon name="gym" size={25} /></div>
    <div className="fc-visit-body"><span className="fc-caption">VISIT {String(index + 1).padStart(2, '0')} · {visit.label || 'GYM ACCESS'}</span>
      <div className="fc-visit-title"><h3>{visit.name}</h3><strong>{money(visit.amount, visit.currency)}</strong></div>
      <div className="fc-visit-meta"><span><Icon name="calendar" size={16} />{dateLabel(visit.date)}</span>
        {visit.start && <span><Icon name="clock" size={16} />{visit.start.slice(0, 5)}{visit.end ? ` – ${visit.end.slice(0, 5)}` : ''} IST</span>}
        <span><Icon name="user" size={16} />{visit.quantity} {visit.quantity === 1 ? 'visitor' : 'visitors'}</span>
      </div>
    </div>
  </article>
}