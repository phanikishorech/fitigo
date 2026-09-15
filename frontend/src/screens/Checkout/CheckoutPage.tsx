import { useEffect, useMemo, useState } from 'react'
import styles from './checkout.module.css'
import { navigate } from '../../router'
import { fetchCartItems } from '../GymAccess/api'
import type { CartItemResponse } from '../GymAccess/types'
import { checkoutCartWithWallet, fetchWalletBalance, topupWallet } from './api'
import ProfileIconButton from '../../components/ProfileIconButton'

type GymPolicy = {
  gym_id: number
  gym_name: string
  rules: string[]
  important_information: string[]
}

function fmtDate(iso: string) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' })
}

export default function CheckoutPage() {
  const [cart, setCart] = useState<CartItemResponse[]>([])
  const [cartLoading, setCartLoading] = useState(true)
  const [walletLoading, setWalletLoading] = useState(true)

  const [walletBalance, setWalletBalance] = useState<string>('0.00')
  const [walletCurrency, setWalletCurrency] = useState<string>('INR')

  const [policies, setPolicies] = useState<GymPolicy[]>([])
  const [policiesLoading, setPoliciesLoading] = useState(true)

  const [couponCode, setCouponCode] = useState('')
  const [couponMsg, setCouponMsg] = useState<string | null>(null)

  const [topupAmount, setTopupAmount] = useState<number>(500)
  const [topupBusy, setTopupBusy] = useState(false)
  const [payBusy, setPayBusy] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'info' | 'warn' | 'err' | 'success'; msg: string } | null>(null)

  const total = useMemo(() => {
    return cart.reduce((acc, it) => acc + (Number(it.total_price) || 0), 0)
  }, [cart])

  const walletBalanceNum = useMemo(() => {
    const v = Number(walletBalance)
    return Number.isFinite(v) ? v : 0
  }, [walletBalance])

  const canPay = cart.length > 0 && walletBalanceNum >= total

  const reloadCart = async () => {
    setCartLoading(true)
    try {
      const items = await fetchCartItems()
      setCart(items)
    } finally {
      setCartLoading(false)
    }
  }

  const reloadWallet = async () => {
    setWalletLoading(true)
    try {
      const b = await fetchWalletBalance()
      setWalletBalance(b.balance)
      setWalletCurrency(b.currency)
    } finally {
      setWalletLoading(false)
    }
  }

  useEffect(() => {
    reloadCart()
    reloadWallet()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    // Load policies from gym details endpoints (best-effort)
    const gymIds = Array.from(new Set(cart.map((c) => c.gym_id)))
    if (!gymIds.length) {
      setPolicies([])
      setPoliciesLoading(false)
      return
    }

    let cancelled = false
    setPoliciesLoading(true)
    Promise.all(
      gymIds.map((gid) =>
        fetch(`/api/v1/gyms/${gid}/details`)
          .then(async (r) => {
            if (!r.ok) return null
            return (await r.json()) as any
          })
          .catch(() => null)
      )
    )
      .then((rows) => {
        if (cancelled) return
        const out: GymPolicy[] = []
        rows.forEach((d) => {
          if (!d) return
          out.push({
            gym_id: Number(d.gym_id),
            gym_name: String(d.gym_name ?? `Gym #${d.gym_id}`),
            rules: Array.isArray(d.rules) ? d.rules : [],
            important_information: Array.isArray(d.important_information) ? d.important_information : []
          })
        })
        setPolicies(out)
      })
      .finally(() => {
        if (!cancelled) setPoliciesLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [cart])

  const applyCoupon = () => {
    const c = couponCode.trim()
    if (!c) {
      setCouponMsg('Enter a coupon code to apply.')
      return
    }
    // MVP: UI only
    setCouponMsg('Coupons are not enabled yet. This code will not change your total in this MVP.')
  }

  const doTopup = async () => {
    if (topupBusy) return
    setTopupBusy(true)
    setNotice(null)
    try {
      await topupWallet(Number(topupAmount))
      await reloadWallet()
      setNotice({ tone: 'success', msg: 'Wallet recharged successfully.' })
    } catch (e: any) {
      setNotice({ tone: 'err', msg: e?.message ?? 'Unable to recharge wallet.' })
    } finally {
      setTopupBusy(false)
    }
  }

  const payNow = async () => {
    if (payBusy) return
    setPayBusy(true)
    setNotice(null)
    try {
      const res = await checkoutCartWithWallet()
      setNotice({
        tone: 'success',
        msg: `Payment successful. Booking confirmed for ${res.confirmed_items.length} item(s). Wallet balance: ₹${Number(res.wallet_balance_after).toFixed(2)}.`
      })
      await reloadCart()
      await reloadWallet()
      // Take user to profile so they can see Upcoming Visits immediately.
      navigate('/profile')
    } catch (e: any) {
      setNotice({ tone: 'err', msg: e?.message ?? 'Payment failed.' })
    } finally {
      setPayBusy(false)
    }
  }

  return (
    <div className={styles.pageRoot}>
      <header className={styles.navbar}>
        <div>
          <a
            className={styles.logo}
            href="/"
            onClick={(e) => {
              e.preventDefault()
              navigate('/')
            }}
          >
            FitiGo
          </a>
        </div>
        <div style={{ fontWeight: 950 }}>Checkout</div>
        <div className={styles.navRight}>
          <ProfileIconButton className={styles.profileBtn} avatarClassName={styles.profileAvatar} />
          <button
            type="button"
            className={styles.secondaryBtn}
            onClick={() => {
              // Router helper doesn't support -1; do a safe back.
              if (window.history.length > 1) window.history.back()
              else navigate('/nearby')
            }}
          >
            Back
          </button>
        </div>
      </header>

      <main className={styles.content}>
        <div className={styles.container}>
          <div className={styles.grid}>
            <section className={styles.card} aria-label="Checkout details">
              <h1 className={styles.title}>Checkout Details</h1>
              <div className={styles.muted} style={{ marginTop: 6 }}>
                Review policies, apply coupon (optional), and pay using your FitiGo Wallet.
              </div>

              <div style={{ marginTop: 16, borderTop: '1px solid var(--line)' }} />

              <div style={{ marginTop: 16, fontWeight: 950 }}>Your Cart</div>
              {cartLoading ? (
                <div className={styles.muted} style={{ marginTop: 8 }}>
                  Loading cart…
                </div>
              ) : cart.length === 0 ? (
                <div className={styles.muted} style={{ marginTop: 8 }}>
                  Cart is empty. Go back and add items.
                </div>
              ) : (
                <div className={styles.summaryList}>
                  {cart.map((c) => (
                    <div key={c.id} className={styles.itemCard}>
                      <div style={{ fontWeight: 950 }}>{c.booking_type === 'CLASS' ? c.class_name ?? 'Class' : 'Gym Access'}</div>
                      <div className={styles.muted} style={{ marginTop: 6 }}>
                        {c.gym_name ?? `Gym #${c.gym_id}`} · {fmtDate(c.booking_date)} · Members: {c.member_count}
                      </div>
                      {c.preferred_start_time ? (
                        <div className={styles.muted} style={{ marginTop: 4 }}>
                          Preferred time: {c.preferred_start_time}
                        </div>
                      ) : c.start_time && c.end_time ? (
                        <div className={styles.muted} style={{ marginTop: 4 }}>
                          Class time: {c.start_time} - {c.end_time}
                        </div>
                      ) : null}
                      <div style={{ marginTop: 10 }} className={styles.row}>
                        <span className={styles.muted}>Amount</span>
                        <span style={{ fontWeight: 950 }}>₹{Number(c.total_price).toFixed(0)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div style={{ marginTop: 16, borderTop: '1px solid var(--line)' }} />

              <div style={{ marginTop: 16, fontWeight: 950 }}>Apply Coupon</div>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 8 }}>
                <input
                  className={styles.input}
                  placeholder="Enter coupon code"
                  value={couponCode}
                  onChange={(e) => setCouponCode(e.target.value)}
                />
                <button type="button" className={styles.secondaryBtn} onClick={applyCoupon}>
                  Apply
                </button>
              </div>
              {couponMsg ? (
                <div className={`${styles.notice} ${styles.noticeWarn}`} style={{ marginTop: 10 }}>
                  <div className={styles.muted}>{couponMsg}</div>
                </div>
              ) : null}

              <div style={{ marginTop: 16, borderTop: '1px solid var(--line)' }} />

              <div style={{ marginTop: 16, fontWeight: 950 }}>Policies</div>
              {policiesLoading ? (
                <div className={styles.muted} style={{ marginTop: 8 }}>
                  Loading policies…
                </div>
              ) : policies.length === 0 ? (
                <div className={styles.muted} style={{ marginTop: 8 }}>
                  Policies not available.
                </div>
              ) : (
                <div style={{ marginTop: 8, display: 'grid', gap: 12 }}>
                  {policies.map((p) => (
                    <div key={p.gym_id} className={styles.itemCard}>
                      <div style={{ fontWeight: 950 }}>{p.gym_name}</div>
                      {p.rules?.length ? (
                        <>
                          <div className={styles.muted} style={{ marginTop: 8, fontWeight: 850 }}>
                            Club Policy
                          </div>
                          <ul className={styles.muted} style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                            {p.rules.slice(0, 8).map((r, i) => (
                              <li key={i}>{r}</li>
                            ))}
                          </ul>
                        </>
                      ) : null}
                      {p.important_information?.length ? (
                        <>
                          <div className={styles.muted} style={{ marginTop: 10, fontWeight: 850 }}>
                            Important Information
                          </div>
                          <ul className={styles.muted} style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                            {p.important_information.slice(0, 8).map((r, i) => (
                              <li key={i}>{r}</li>
                            ))}
                          </ul>
                        </>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </section>

            <aside className={styles.card} aria-label="Payment summary">
              <div style={{ fontWeight: 950 }}>Price Details</div>
              <div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
                <div className={styles.row}>
                  <span className={styles.muted}>Cart Total</span>
                  <span style={{ fontWeight: 950 }}>₹{Number(total).toFixed(2)}</span>
                </div>
                <div className={styles.row}>
                  <span className={styles.muted}>Convenience Fee</span>
                  <span style={{ fontWeight: 950 }}>₹0.00</span>
                </div>
                <div style={{ borderTop: '1px solid var(--line)', marginTop: 6 }} />
                <div className={styles.row}>
                  <span style={{ fontWeight: 950 }}>Total Amount</span>
                  <span style={{ fontWeight: 950 }}>₹{Number(total).toFixed(2)}</span>
                </div>
              </div>

              <div style={{ marginTop: 16, borderTop: '1px solid var(--line)' }} />

              <div style={{ marginTop: 16, fontWeight: 950 }}>Payment</div>
              <div className={styles.muted} style={{ marginTop: 6 }}>
                Wallet is the only payment option in this MVP.
              </div>

              <div className={styles.notice} style={{ marginTop: 12 }}>
                <div style={{ fontWeight: 900 }}>FitiGo Wallet</div>
                {walletLoading ? (
                  <div className={styles.muted} style={{ marginTop: 6 }}>
                    Loading wallet…
                  </div>
                ) : (
                  <div className={styles.muted} style={{ marginTop: 6 }}>
                    Balance: ₹{Number(walletBalance).toFixed(2)} {walletCurrency}
                  </div>
                )}
              </div>

              {!walletLoading && walletBalanceNum < total ? (
                <div className={`${styles.notice} ${styles.noticeErr}`} style={{ marginTop: 12 }}>
                  <div style={{ fontWeight: 900 }}>Insufficient balance</div>
                  <div className={styles.muted} style={{ marginTop: 6 }}>
                    Add money to your wallet to complete payment.
                  </div>
                </div>
              ) : null}

              <div style={{ marginTop: 12, display: 'grid', gap: 10 }}>
                <div style={{ display: 'flex', gap: 10 }}>
                  <input
                    className={styles.input}
                    type="number"
                    min={1}
                    value={String(topupAmount)}
                    onChange={(e) => setTopupAmount(Number(e.target.value || 0))}
                    placeholder="Top up amount"
                    style={{ flex: 1 }}
                  />
                  <button type="button" className={styles.secondaryBtn} onClick={doTopup} disabled={topupBusy}>
                    {topupBusy ? 'Recharging…' : 'Recharge'}
                  </button>
                </div>

                <button type="button" className={styles.primaryBtn} onClick={payNow} disabled={payBusy || !canPay}>
                  {payBusy ? 'Processing…' : `Pay ₹${Number(total).toFixed(2)} with Wallet`}
                </button>
              </div>

              {notice ? (
                <div
                  className={`${styles.notice} ${
                    notice.tone === 'err' ? styles.noticeErr : notice.tone === 'warn' ? styles.noticeWarn : ''
                  }`}
                  style={{ marginTop: 12 }}
                >
                  <div className={styles.muted}>{notice.msg}</div>
                </div>
              ) : null}
            </aside>
          </div>
        </div>
      </main>
    </div>
  )
}
