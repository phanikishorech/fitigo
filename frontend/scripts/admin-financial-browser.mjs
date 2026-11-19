// Isolated context, intercepted APIs. Never reads or mutates real customer data.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let seq = 0, fail = false
const payoutFlow = process.env.FITIGO_TEST_PAYOUT_FLOW === '1'
let payout = null, payoutWrites = 0
const pending = new Map(), errors = [], calls = []
const unknown = { value: null, status: 'NOT_CONFIGURED', reason: 'Agreement and accounting policy are not configured.' }
const category = { sales_count: 1, sales_value: '500.00', gateway_funded_value: '500.00', wallet_funded_value: '0.00', recognized_revenue: unknown, active: 1, expired: 0, expiring_30_days: 0 }
function report(q) {
  return { version: 1, date_from: q.get('date_from'), date_to: q.get('date_to'), mode: q.get('mode') || 'test', source: q.get('source'), gym_id: q.has('gym_id') ? Number(q.get('gym_id')) : null, currency: 'INR', timezone: 'Asia/Kolkata', generated_at: '2026-11-13T10:00:00Z',
    options: [{ id: 1, name: 'Fixture gym' }], platform: { total_users: 4, new_users: 1, new_customers: 1, active_gyms: 1, pending_gyms: 0, new_gyms: 0, completed_visits: 1, upcoming_bookings: 4 },
    revenue: { attended_booking_value: '150.00', attended_wallet_funded_value: '40.00', attended_booking_count: 1, recognized_total: unknown, fitigo_booking_income: unknown, no_show_count: 1, no_show_gross: '150.00', no_show_fitigo_income: unknown, no_show_owner_share: unknown },
    bookings: { total: 7, confirmed: 4, cancelled: 2, attended: 1, no_show: 1, pending: 1, expired: 0, upcoming: 2, cancellation_rate: 28.57, no_show_rate: 50 },
    memberships: { categories: { SINGLE_GYM: category, MULTI_GYM: { ...category, sales_value: '1000.00' } }, transfers: 1, renewals: unknown, plan_popularity: [{ membership_type: 'SINGLE_GYM', plan_id: 1, platform_plan_id: null, sales: 1, sales_value: '500.00' }] },
    payments: { applicable: true, dated_collections: { ...unknown, reason: 'Capture dates are unavailable.' }, undated: [{ provider: 'RAZORPAY', gross_collections: '110.00', refunds_recorded: '0.00', net_recorded: '110.00', successful_payments: 1, membership_collections: '0.00', recharge_collections: '0.00' }], attempts: { total: 3, successful: 1, pending: 1, failed: 1, success_rate: 33.33, basis: 'First observed in range, not capture date.' }, gateway_fee: unknown, mismatches: 0, review_required: 0 },
    wallet: { applicable: true, outstanding: '300.00', stored_balance: '300.00', credits: '300.00', spending: '40.00', ledger_net: '300.00', reconciliation_difference: '0.00', mismatched_accounts: 0, status: 'RECONCILED', unclassified_mode_balance: '0.00', debits: '40.00', booking_spending: '40.00', membership_spending: '0.00', unallocated_spending: '0.00', cancellation_credits: '300.00', opening_ledger_balance: '40.00', closing_ledger_balance: '300.00', movements_by_type: [{ txn_type: 'CANCELLATION_CREDIT', direction: 'IN', amount: '300.00', count: 2 }], promotional_credits: unknown, adjustments: unknown, expirations: unknown, source_liability: unknown, liability_aging: unknown },
    settlements: { total_payable: unknown, attended_payable: unknown, wallet_funded_attended_payable: unknown, membership_payable: unknown, no_show_payable: unknown, paid: unknown, pending: unknown, adjustments: unknown, outstanding: unknown },
    customers: { active: 1, repeat: 0, previous_active: 1, retained: 1, retention_rate: 100, visits_per_active: 1, membership_conversion: unknown, most_active: [{ user_id: 1, visits: 1 }] },
    gyms: [{ id: 1, name: 'Fixture gym', status: 'APPROVED', is_active: true, visits: 1, attended_value: '150.00', single_membership_sales_value: '500.00', owner_payable: null, utilization: null }],
    series: [{ date: q.get('date_from'), attended_value: '150.00', visits: 1, membership_sales_value: '1500.00', no_show_gross: '150.00', wallet_credits: '300.00', wallet_spending: '40.00' }],
    definitions: { attended: 'Verified value once at first check-in. Not platform profit.', bookings: 'Scheduled-date booking cohort.', wallet: 'Current liability includes holds; subtract debits.', membership_sales: 'Sales once at creation, not repeated visits.' } }
}
function fixture(url) {
  const path = url.pathname
  if (path.endsWith('/auth/session')) return { user: { id: 1, first_name: 'Fixture', last_name: 'Admin', email: 'admin@example.test' }, roles: ['ADMIN'] }
  if (path.endsWith('/notifications/inbox')) return { items: [], total: 0, unread_count: 0 }
  if (path.endsWith('/notifications/me')) return []
  if (path.endsWith('/cart/summary')) return { count: 0, total: '0.00', currency: 'INR' }
  if (path.endsWith('/marketplace/financial-summary')) return { available: true, mode: url.searchParams.get('mode'), owners: [{ id: 2, name: 'Historical owner' }], processing_enabled: false, live_processing_enabled: false, statutory_reporting_enabled: false, fee_pending_count: 1, undated_capture_count: 1, total: 1, totals: { attended_commission: '15.00', gym_gross_share: '85.00', total_owner_payable: null, multi_gym_fitigo_earnings: null }, items: [{ id: 'allocation-fixture', transaction_reference: 'payment-fixture', customer_id: 1, customer_name: 'Fixture customer', gym_id: 1, gym_name: 'Fixture gym', owner_user_id: 2, owner_name: 'Historical owner', category: 'ATTENDED_BOOKING', visitor_index: 0, eligible_amount: '100.00', agreement_version: 1, agreement_version_id: 1, gym_gross_share: '85.00', fitigo_gross_commission: '15.00', gateway_fee: null, gym_gateway_fee_share: null, fitigo_gateway_fee_share: null, owner_net: null, payout_status: 'FEE_PENDING', payment_references: [], occurred_at: '2026-11-13T10:00:00Z', reversed: false }], monthly_visits: [], definitions: { basis: 'Immutable allocation evidence only.' } }
  if (path.endsWith('/marketplace/payouts')) return { total: payout ? 1 : 0, items: payout ? [payout] : [] }
  if (path.endsWith('/marketplace/historical-review')) return { read_only: true, notice: 'Review only. No historical adjustment is posted.', items: [], has_more: false, inconsistent_source_events: 0, unclassified_environment_bookings: 1, unclassified_environment_memberships: 1 }
  if (path.endsWith('/reports/wallet-ledger')) return { total: 1, items: [{ id: 1, account_id: 1, direction: 'IN', txn_type: 'CANCELLATION_CREDIT', amount: '300.00', currency: 'INR', checkout_id: null, reference: 'fixture-cancellation', created_at: '2026-11-13T10:00:00Z' }] }
  if (/\/(dashboard\/summary|analytics|reports\/financial)$/.test(path)) { assert.equal(url.searchParams.get('financial'), 'true'); calls.push(Object.fromEntries(url.searchParams)); return fail ? { fixtureStatus: 503, detail: 'Unavailable' } : report(url.searchParams) }
  throw Error(`Unexpected API ${path}`)
}
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++seq, timer = setTimeout(() => reject(Error(method)), 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value }
async function until(expression) { for (let i = 0; i < 200; i++) { if (await evaluate(expression)) return; await new Promise(r => setTimeout(r, 80)) } throw Error(`${expression}; ${await evaluate('document.body?.innerText')}; ${errors}`) }
async function click(text) { await until(`Array.from(document.querySelectorAll('main button')).some(b=>b.textContent.trim()===${JSON.stringify(text)} && !b.disabled)`); await evaluate(`Array.from(document.querySelectorAll('main button')).find(b=>b.textContent.trim()===${JSON.stringify(text)}).click()`) }
async function select(label, value) { await evaluate(`(()=>{const el=Array.from(document.querySelectorAll('label')).find(l=>l.textContent.includes(${JSON.stringify(label)})).querySelector('select');el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change',{bubbles:true}))})()`) }
ws.onmessage = async event => {
  const m = JSON.parse(event.data), item = pending.get(m.id)
  if (item) { clearTimeout(item.timer); pending.delete(m.id); m.error ? item.reject(Error(m.error.message)) : item.resolve(m.result) }
  if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.text)
  if (m.method !== 'Fetch.requestPaused') return
  const { requestId, request } = m.params
  try {
    let data
    if (payoutFlow && request.method === 'POST') {
      const body = JSON.parse(request.postData), url = new URL(request.url)
      assert.ok(Object.keys(request.headers).some(key => key.toLowerCase() === 'idempotency-key'))
      if (url.pathname.endsWith('/marketplace/payouts')) {
        assert.equal(payout, null); assert.equal(body.items[0].allocation_id, 'allocation-fixture'); assert.equal(body.items[0].amount, '84.00')
        payout = { id: 'payout-fixture', mode: 'test', gym_id: 1, owner_user_id: 2, category: 'ATTENDED_BOOKING', amount: '84.00', entitlement_amount: '84.00', deduction_amount: '0.00', status: 'PENDING_APPROVAL', version: 1, payment_reference: null, paid_at: null }
      } else {
        assert.ok(url.pathname.endsWith('/payouts/payout-fixture/transition'))
        assert.equal(body.expected_version, payout.version)
        if (body.status === 'PAID') { assert.equal(body.payment_evidence.amount, '84.00'); assert.equal(body.payment_evidence.owner_user_id, 2); assert.ok(body.payment_evidence.document_reference); payout.payment_reference = body.payment_evidence.reference; payout.paid_at = body.payment_evidence.paid_at }
        else { assert.equal(body.payment_evidence, null); assert.equal(payout.payment_reference, null) }
        payout.status = body.status; payout.version++
      }
      payoutWrites++; data = payout
    } else {
      assert.equal(request.method, 'GET', 'Financial reports must be read-only')
      data = fixture(new URL(request.url))
      if (payoutFlow && new URL(request.url).pathname.endsWith('/marketplace/financial-summary')) {
        data.items[0].owner_net = '84.00'; data.items[0].payout_status = payout?.status || 'AVAILABLE'
        data.items[0].gateway_fee = '2.00'; data.items[0].gym_gateway_fee_share = data.items[0].fitigo_gateway_fee_share = '1.00'
      }
    }
    await command('Fetch.fulfillRequest', { requestId, responseCode: data.fixtureStatus || 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(data)).toString('base64') })
  } catch (e) { errors.push(e.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
}
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fitigo:access_token','isolated-financial-fixture');window.exports=[];URL.createObjectURL=b=>{window.exports.push(b);return 'blob:fixture'};URL.revokeObjectURL=()=>{};HTMLAnchorElement.prototype.click=function(){if(!this.download)HTMLElement.prototype.click.call(this)}` })
  await command('Page.navigate', { url: origin + '/admin/dashboard' })
  await until(`document.body?.innerText.includes('Attended individual booking value')`)
  if (payoutFlow) {
    async function fill(label, value) { await evaluate(`(()=>{const el=Array.from(document.querySelectorAll('dialog label')).find(l=>l.textContent.includes(${JSON.stringify(label)})).querySelector('input,textarea');Object.getOwnPropertyDescriptor(el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('input',{bubbles:true}))})()`) }
    await click('Request approval'); await until(`document.querySelector('dialog[open]')!==null`)
    await fill('Reason', 'Reviewed fixture entitlement'); await click('Confirm recorded action')
    await until(`document.querySelector('dialog[open]')===null && document.body.innerText.includes('PENDING_APPROVAL')`)
    assert.equal(payoutWrites, 1); assert.equal(payout.payment_reference, null)
    for (const status of ['APPROVED', 'PROCESSING', 'PAID']) {
      await click('Review'); await until(`document.querySelector('dialog[open]')!==null`)
      await fill('Reason', 'Reviewed fixture payout evidence')
      if (status === 'PAID') {
        await fill('Actual bank payment reference', 'BANK-FIXTURE-123')
        await fill('Protected bank evidence document reference', 'protected-document-fixture')
        await fill('Actual payment date/time', '2026-11-12T12:00:00')
      }
      await click('Confirm recorded action')
      await until(`document.querySelector('dialog[open]')===null && document.body.innerText.includes('${status}')`)
      assert.equal(payout.status, status)
      if (status !== 'PAID') assert.equal(payout.payment_reference, null)
    }
    assert.equal(payoutWrites, 4); assert.equal(payout.payment_reference, 'BANK-FIXTURE-123')
    assert.deepEqual(errors, [])
    console.log('PASS mocked payout request/approval/processing/actual-payment evidence UI. All writes intercepted.')
  } else {
  assert.ok(await evaluate(`document.body.innerText.includes('Not configured') && document.body.innerText.includes('₹300.00')`))
  for (const width of [360, 768, 1440]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 640 })
    assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true, `dashboard width ${width}`)
  }
  await command('Page.navigate', { url: origin + '/admin/analytics' })
  await until(`document.body?.innerText.includes('Gym performance')`)
  for (const [tab, expected] of [['Payments', 'capture date unavailable'], ['Wallet', 'Wallet ledger'], ['Bookings & attendance', 'Booking outcome distribution'], ['Memberships', 'Plan popularity'], ['Gyms', 'Gym performance'], ['Customers', 'Most active customer accounts'], ['Settlements', 'No settlement history']]) {
    await click(tab); await until(`document.body.innerText.includes(${JSON.stringify(expected)})`)
  }
  await select('Payment environment', 'live'); await until(`document.body.innerText.includes('Production / live records only')`)
  assert.equal(calls.at(-1).mode, 'live')
  await select('Funding source', 'WALLET'); await until(`document.querySelector('select') !== null`)
  await new Promise(r => setTimeout(r, 300)); assert.equal(calls.at(-1).source, 'WALLET')
  await click('Export event-date report CSV'); await until('window.exports.length===1')
  const csv = await evaluate('window.exports[0].text()'); assert.ok(csv.includes('live') && csv.includes('first check-in date'))
  await command('Page.navigate', { url: origin + '/admin/reports?section=wallet' })
  await until(`document.body?.innerText.includes('fixture-cancellation')`)
  for (const width of [360, 768, 1440]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 640 })
    assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true, `wallet width ${width}`)
  }
  fail = true; await click('Yesterday'); await until(`document.body.innerText.includes('Unable to load')`)
  assert.deepEqual(errors, [])
  console.log('PASS financial dashboard/8 analytics sections/reports, unknown policies, ledger, mode/source filters, CSV, errors and responsive widths. All APIs mocked.')
  }
} finally { ws.close(); await target.dispose() }