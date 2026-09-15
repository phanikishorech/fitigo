import { authFetch } from '../../auth'
import type { CartItemResponse } from '../GymAccess/types'

export type WalletBalanceResponse = { balance: string; currency: string }

export type WalletTopupResponse = {
  transaction: {
    id: number
    direction: string
    txn_type: string
    amount: string
    currency: string
    reference?: string | null
    description?: string | null
    created_at: string
  }
  balance: string
  currency: string
}

export type CartWalletCheckoutResponse = {
  confirmed_items: CartItemResponse[]
  total_amount: string
  currency: string
  wallet_balance_before: string
  wallet_balance_after: string
  wallet_transaction_id: number
  booking_ids?: number[]
}

export async function fetchWalletBalance(): Promise<WalletBalanceResponse> {
  const r = await authFetch('/api/v1/wallet/balance')
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data?.detail ?? 'Failed to load wallet balance')
  }
  return (await r.json()) as WalletBalanceResponse
}

export async function topupWallet(amount: number): Promise<WalletTopupResponse> {
  const r = await authFetch('/api/v1/wallet/topup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ amount })
  })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data?.detail ?? 'Failed to top up wallet')
  }
  return (await r.json()) as WalletTopupResponse
}

export async function checkoutCartWithWallet(): Promise<CartWalletCheckoutResponse> {
  const r = await authFetch('/api/v1/cart/checkout/wallet', { method: 'POST' })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data?.detail ?? 'Failed to pay with wallet')
  }
  return (await r.json()) as CartWalletCheckoutResponse
}
