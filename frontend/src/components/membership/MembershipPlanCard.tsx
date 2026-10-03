import type { ReactNode } from 'react'
import { money } from '../../services/client'
import { planDuration, type PlatformPlan } from '../../services/platformMembershipService'
import Icon from '../common/Icon'
import { Badge, Button, EmptyState, Link, Skeleton } from '../common/UI'
import { MembershipPanel } from './MembershipUI'

export function PriceDisplay({ plan }: { plan: PlatformPlan }) {
  return <div className="fm-plan-pricing">
    {plan.offer && <del><span className="srOnly">Original price </span>{money(plan.base_price, plan.currency)}</del>}
    <div className="fm-plan-price"><span className="srOnly">Current price </span>{money(plan.final_price, plan.currency)}</div>
    <span className="fm-muted">for {planDuration(plan)}</span>
    {plan.offer && <div className="fm-plan-discount"><Badge tone="success">{plan.discount_percentage !== null ? `${Number(plan.discount_percentage)}% OFF` : `Save ${money(plan.discount_amount, plan.currency)}`}</Badge></div>}
  </div>
}

export function MembershipPlanCard({ plan, children }: { plan: PlatformPlan; children?: ReactNode }) {
  return <MembershipPanel className="fm-plan-card">
    {(plan.badge || plan.offer?.title) && <div className="fm-plan-badges">{plan.badge && <Badge>{plan.badge}</Badge>}{plan.offer?.title && <Badge tone="success">{plan.offer.title}</Badge>}</div>}
    <h2>{plan.name}</h2>{plan.description && <p className="fm-muted">{plan.description}</p>}
    <PriceDisplay plan={plan} />
    <ul className="fm-plan-benefits">
      <li><Icon name="check" size={18} /><span>Access eligible FitiGo partner gyms</span></li>
      <li><Icon name="check" size={18} /><span>{plan.access_rule.daily_access} daily access per active day</span></li>
      {plan.benefits.map((benefit, index) => <li key={`${index}:${benefit}`}><Icon name="check" size={18} /><span>{benefit}</span></li>)}
    </ul>
    {children && <div className="fm-plan-action">{children}</div>}
  </MembershipPanel>
}

export function PlanSkeleton() { return <div className="fm-plan-loading"><Skeleton cards={4} /></div> }
export function PlanEmptyState() {
  return <EmptyState title="Multi-Gym plans aren't available right now." description="Please check back later or explore gyms for Single-Gym membership options." action={<Link to="/explore" className="fg-button fg-button--primary">Explore Gyms</Link>} />
}
export function PlanErrorState({ message, retry }: { message: string; retry: () => void }) {
  return <div role="alert"><EmptyState title={message} action={<Button variant="secondary" onClick={retry}>Try Again</Button>} /></div>
}