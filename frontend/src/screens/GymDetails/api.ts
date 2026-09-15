import type { GymDetailsResponse } from './types'
import { authFetch } from '../../auth'

export type GymMembershipPlan = {
  id: number
  gym_id: number
  name: string
  description: string | null
  duration_days: number
  price: string
  currency: string
  is_active: boolean
}

export type PurchaseMembershipResponse = {
  id: number
  user_id: number
  gym_id: number
  plan_id: number
  status: string
  start_at: string
  end_at: string
  paid_amount: string
  currency: string
}

async function jsonOrThrow<T>(r: Response): Promise<T> {
  const data = await r.json().catch(() => ({} as any))
  if (!r.ok) {
    const detail = (data as any)?.detail
    if (typeof detail === 'string' && detail.trim()) throw new Error(detail)
    throw new Error('Request failed')
  }
  return data as T
}

export async function fetchGymDetails(gymId: number): Promise<GymDetailsResponse> {
  // Use authFetch so membership_access reflects the logged-in user (if any).
  const r = await authFetch(`/api/v1/gyms/${gymId}/details`)
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data?.detail ?? 'Failed to load gym')
  }
  return (await r.json()) as GymDetailsResponse
}

export async function fetchGymMembershipPlans(gymId: number): Promise<GymMembershipPlan[]> {
  const r = await fetch(`/api/v1/memberships/gyms/${gymId}/plans`)
  return await jsonOrThrow<GymMembershipPlan[]>(r)
}

export async function purchaseGymMembershipPlan(gymId: number, planId: number): Promise<PurchaseMembershipResponse> {
  const r = await authFetch(`/api/v1/memberships/gyms/${gymId}/purchase`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan_id: planId })
  })

  if (!r.ok) {
    // Some endpoints may return plain-text on errors.
    const txt = await r.text().catch(() => '')
    try {
      const j = JSON.parse(txt)
      const detail = (j as any)?.detail
      if (typeof detail === 'string' && detail.trim()) throw new Error(detail)
      throw new Error('Failed to purchase membership')
    } catch {
      throw new Error(txt || 'Failed to purchase membership')
    }
  }
  return (await r.json()) as PurchaseMembershipResponse
}
