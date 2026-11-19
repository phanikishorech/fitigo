// Separate browser storage; all API requests and payment SDKs are mocked.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, record = null, creates = 0, cancelPending = false, conflict = false, recoveryFails = false
let supportPayload = null, supportCreates = 0
let verifyFails = false
const pending = new Map(), errors = [], keys = []
const user = { id: 1, first_name: 'Recovery', last_name: 'Fixture', email: 'recovery@example.test' }
const plan = { id: 1, code: 'monthly', name: 'Monthly fixture membership', membership_type: 'MULTI_GYM', duration_value: 1, duration_unit: 'MONTH', base_price: '2199.00', final_price: '2199.00', discount_amount: '0.00', currency: 'INR', offer: null, benefits: [], is_active: true, version: 1, access_rule: { scope: 'ELIGIBLE_PARTNER_GYMS', daily_access: 1 }, pause_rule: { allowed: true, max_pause_days: 3 }, purchase_available: true }
const safelyClosed = () => record?.status === 'CANCELLED' && record.replacement_safe
function fixture(path, method, body, headers) {
  if (path.endsWith('/auth/session')) return { user, roles: ['CUSTOMER'] }
  if (path.endsWith('/users/me')) return user
  if (path.endsWith('/cart/summary')) return { count: 0, total: '0.00', currency: 'INR' }
  if (path.endsWith('/payments/config')) return { enabled: true, gateway_required: true, mode: 'test', provider: 'CASHFREE' }
  if (path.includes('/memberships/orders/')) return { id: '11111111-1111-4111-8111-111111111111', plan, current_plan: conflict ? { ...plan, id: 2, name: 'Three-month selected membership', final_price: '5499.00', base_price: '5499.00', duration_value: 3 } : plan, created_at: '2026-11-18T00:00:00Z', payment_status: conflict ? 'NOT_STARTED' : record?.status || 'NOT_STARTED', membership_id: null, payment_mode: 'CASHFREE', quote_token: 'a'.repeat(64), payment_available: true }
  if (path.endsWith('/payments/membership-checkout')) return { checkout: safelyClosed() ? null : record, matches_selection: !conflict }
  if (path.endsWith('/payments/quote')) {
    const available = record && !safelyClosed() ? 0 : 49
    const wallet = body.use_wallet ? available : 0
    return { total_amount: '2199.00', wallet_amount: wallet.toFixed(2), gateway_amount: (2199 - wallet).toFixed(2), wallet_balance: '49.00', available_wallet_balance: available.toFixed(2), reserved_balance: (49 - available).toFixed(2), wallet_unavailable_reason: null, provider: 'CASHFREE', currency: 'INR', mode: 'test' }
  }
  if (path.endsWith('/payments/checkouts') && method === 'POST') {
    assert.ok(!record || safelyClosed(), 'must never replace an unresolved payment')
    creates++; keys.push(Object.entries(headers).find(([key]) => key.toLowerCase() === 'idempotency-key')?.[1])
    const wallet = body.use_wallet ? 49 : 0
    record = { id: `checkout-${creates}`, kind: 'MULTI_GYM', plan_name: plan.name, provider: 'CASHFREE', mode: 'test', environment: 'sandbox', status: 'PENDING', total_amount: '2199.00', wallet_amount: wallet.toFixed(2), gateway_amount: (2199-wallet).toFixed(2), amount: (2199-wallet).toFixed(2), amount_minor: (2199-wallet)*100, currency: 'INR', wallet_status: wallet ? 'HELD' : 'NONE', can_pay: true, can_cancel: false, can_request_cancel: true, replacement_safe: false, cancellation_requested: false, booking_ids: [], membership_id: null, gateway_order_id: 'gateway-fixture', payment_session_id: 'session-fixture' }
    record.recovery_status = 'RESUMABLE'; record.can_contact_support = true
    record.order_reference = '11111111-1111-4111-8111-111111111111'
    return record
  }
  if (path.endsWith('/cancel')) {
    record = cancelPending ? { ...record, status: 'FAILED', recovery_status: 'CANCELLATION_PENDING', can_pay: false, cancellation_requested: true, payment_blocked_reason: 'CANCELLATION_PENDING' }
      : { ...record, status: 'CANCELLED', recovery_status: 'SAFELY_CLOSED', wallet_status: 'RELEASED', can_pay: false, replacement_safe: true, can_request_cancel: false, cancellation_requested: true, payment_blocked_reason: 'CANCELLED' }
    return record
  }
  if (path.endsWith('/resume-membership')) {
    record = { ...record, can_pay: true, can_resume_reserved_membership: false, recovery_status: 'RESUMABLE', payment_blocked_reason: null }
    return record
  }
  if (path.includes('/payments/checkouts/')) return record
  if (path.endsWith('/meta/support')) return { ticketing_available: true, email: null, message: 'Use in-app support.' }
  if (path.endsWith('/support/tickets') && method === 'POST') { supportCreates++; supportPayload = body; return { id: 7 } }
  if (path.endsWith('/support/tickets')) return { items: [], total: 0 }
  if (path.endsWith('/support/tickets/7')) return { id: 7, subject: supportPayload.subject, status: 'OPEN', version: 1, messages: [{ id: 1, author_kind: 'REQUESTER', body: supportPayload.body, created_at: '2026-11-18T00:00:00Z' }], message_total: 1, can_reply: true, can_change_status: false }
  if (path.includes('/notifications')) return path.endsWith('/unread-count') ? { count: 0 } : { items: [], total: 0, unread_count: 0 }
  throw Error(`Unexpected API ${method} ${path}`)
}
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 15000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text); return result.result.value }
async function until(expression) { for (let i=0;i<150;i++) { if (await evaluate(`!!(${expression})`)) return; await new Promise(resolve=>setTimeout(resolve,100)) } throw Error(`${expression}: ${await evaluate('document.body.innerText')}; ${errors}`) }
const button = label => `Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()===${JSON.stringify(label)})`
async function click(label) { await until(`${button(label)} && !${button(label)}.disabled`); await evaluate(`${button(label)}.click()`) }
ws.onmessage = async event => {
  const message = JSON.parse(event.data), item = pending.get(message.id)
  if (item) { clearTimeout(item.timer); pending.delete(message.id); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result) }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
  if (message.method !== 'Fetch.requestPaused') return
  const { requestId, request } = message.params
  try {
    const path = new URL(request.url).pathname
    if (!path.startsWith('/api/v1/')) throw Error('Unexpected external gateway request')
    const fail = (path.endsWith('/payments/membership-checkout') && recoveryFails) || (path.endsWith('/verify') && verifyFails)
    const body = fail ? { detail: 'Fixture recovery unavailable' } : fixture(path, request.method, request.postData ? JSON.parse(request.postData) : {}, request.headers)
    await command('Fetch.fulfillRequest', { requestId, responseCode: fail ? 503 : 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') })
  } catch (error) {
    if (error.message.includes('Invalid InterceptionId')) return
    errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }).catch(()=>{})
  }
}
try {
  await command('Runtime.enable'); await command('Page.enable')
  await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }, { urlPattern: '*cashfree.com/*' }, { urlPattern: '*razorpay.com/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fitigo:access_token','recovery-fixture');window.opens=0;window.Cashfree=()=>({checkout:async()=>{window.opens++;return {error:{message:'closed'}}}})` })
  const url = origin + '/membership/checkout?orderId=11111111-1111-4111-8111-111111111111'
  await command('Page.navigate', { url })
  await until(`${button('Continue to secure payment')} && !${button('Continue to secure payment')}.disabled`)
  await evaluate(`document.querySelector('[aria-label="Payment method"] input[type=checkbox]').click()`)
  await until(`document.querySelector('[aria-label="Payment method"]').innerText.includes('2,150') && !${button('Continue to secure payment')}.disabled`)
  await click('Continue to secure payment'); await until('window.opens===1')
  await until(`${button('Continue payment')} && !${button('Continue payment')}.disabled`)
  assert.equal(await evaluate(`document.querySelector('[aria-label="Your selected plan"]').innerText.includes('Not started for this plan')`), false)
  assert.equal(creates, 1); assert.equal(record.wallet_amount, '49.00')
  await command('Page.reload'); await until(`${button('Resume payment')} && !${button('Resume payment')}.disabled`)
  assert.equal(await evaluate(`!!document.querySelector('[aria-label="Payment method"]')`), false)
  assert.equal(await evaluate('window.opens'), 0)
  await click('Resume payment'); await until('window.opens===1'); assert.equal(creates, 1)
  conflict = true
  await command('Page.reload'); await until(`document.body.innerText.includes('different selection')`)
  cancelPending = true
  await click('Cancel and change'); await click('Confirm cancellation')
  await until(`document.body.innerText.includes('Cancellation is being checked')`)
  assert.equal(await evaluate(`!!${button('Resume payment')}`), false)
  assert.equal(await evaluate(`!!${button('Review plan and payment method')}`), false)
  assert.equal(record.wallet_status, 'HELD')
  await command('Page.reload'); await until(`document.body.innerText.includes('Cancellation is being checked')`)
  assert.equal(await evaluate('window.opens'), 0)
  record = { ...record, status: 'CANCELLED', recovery_status: 'SAFELY_CLOSED', wallet_status: 'RELEASED', replacement_safe: true, can_request_cancel: false, payment_blocked_reason: 'CANCELLED' }
  conflict = false
  await click('Refresh payment status'); await click('Review plan and payment method')
  await until(`${button('Continue to secure payment')} && !${button('Continue to secure payment')}.disabled`)
  assert.ok(await evaluate(`document.querySelector('[aria-label="Payment method"]').innerText.includes('Available balance: ₹49')`))
  await click('Continue to secure payment'); await until('window.opens===1')
  assert.equal(creates, 2); assert.equal(record.wallet_amount, '0.00'); assert.notEqual(keys[0], keys[1])
  assert.ok(keys.every(Boolean))
  recoveryFails = true
  await command('Page.reload'); await until(`${button('Retry payment recovery')}`)
  assert.equal(await evaluate(`!!${button('Continue to secure payment')}`), false)
  recoveryFails = false
  await click('Retry payment recovery'); await until(`${button('Resume payment')}`)
  assert.equal(creates, 2)
  conflict = true
  record = { ...record, provider: 'RAZORPAY', status: 'FAILED', recovery_status: 'RESOLUTION_REQUIRED', can_pay: false, can_cancel: false, can_request_cancel: false, wallet_status: 'HELD', wallet_amount: '49.00', gateway_amount: '2150.00', amount: '2150.00', payment_blocked_reason: 'WALLET_HOLD_RECONCILING', order_reference: 'original-monthly-order', payment_reference: 'pay_original', wallet_hold_expires_at: '2026-11-17T00:00:00Z' }
  await command('Page.reload'); await until(`${button('Contact support')}`)
  assert.equal(await evaluate(`!!${button('Resume payment')} || !!${button('Cancel and change')}`), false)
  assert.ok(await evaluate(`document.querySelector('[aria-label="Your selected plan"]').innerText.includes('5,499') && document.body.innerText.includes('Not started for this plan')`))
  assert.ok(await evaluate(`document.querySelector('[aria-label="Original payment breakdown"]').innerText.includes('2,199')`))
  assert.equal(await evaluate(`document.querySelector('.pr-details').open`), false)
  for (const width of [1440, 768, 390, 320]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 768 })
    assert.ok(await evaluate(`document.documentElement.scrollWidth <= innerWidth + 1`), `no horizontal overflow at ${width}`)
    assert.ok(await evaluate(`document.querySelector('.pr-mode').getBoundingClientRect().width > 0`))
  }
  await click('Contact support'); await until(`document.querySelector('textarea[name=body]')`)
  const draft = await evaluate(`document.querySelector('textarea[name=body]').value`)
  for (const value of [record.id, 'original-monthly-order', 'pay_original', '2199.00', '49.00', '2150.00', 'RESOLUTION_REQUIRED']) assert.ok(draft.includes(value))
  assert.ok(!draft.includes('session-fixture'))
  await click('Submit support request'); await until(`document.body.innerText.includes('Request #7:')`)
  assert.equal(supportCreates, 1); assert.equal(record.wallet_status, 'HELD'); assert.equal(creates, 2)
  record.can_resume_reserved_membership = true
  record.key_id = 'rzp_test_fixture'
  await command('Page.reload'); await until(`${button('Resume original membership')}`)
  await evaluate(`window.Razorpay=class { constructor(options){this.options=options} on(){} open(){window.opens++;window.resumedOrder=this.options.order_id;this.options.modal.ondismiss()} }`)
  record.razorpay_order_id = record.gateway_order_id
  await click('Resume original membership')
  await until(`document.querySelector('[aria-label="Confirm original membership"]')`)
  assert.equal(await evaluate('window.opens'), 0)
  await click('Confirm and resume original payment'); await until('window.opens===1')
  assert.equal(creates, 2); assert.equal(record.wallet_status, 'HELD')
  assert.equal(await evaluate('window.resumedOrder'), record.gateway_order_id)
  assert.ok(await evaluate(`document.querySelector('[aria-label="Your selected plan"]').innerText.includes('5,499')`))
  // Hosted return must show exact server-verified payment, never an empty cart.
  record = { ...record, id: '22222222-2222-4222-8222-222222222222', provider: 'CASHFREE', status: 'PAID', recovery_status: 'PAID', membership_id: 19, can_pay: false, can_resume_reserved_membership: false, wallet_status: 'DEBITED' }
  await command('Page.navigate', { url: origin + '/checkout?payment_checkout_id=' + record.id })
  await until(`document.querySelector('[aria-label="Payment result"]')?.innerText.includes('Payment confirmed')`)
  assert.ok(await evaluate(`document.body.innerText.includes('Your membership has been activated.') && !!document.querySelector('a[href="/membership/19"]')`))
  assert.equal(await evaluate(`document.body.innerText.includes('Your workout plans')`), false)
  assert.equal(creates, 2)
  await command('Page.reload'); await until(`document.body?.innerText.includes('Payment confirmed')`)
  await evaluate(`sessionStorage.setItem('fitigo:payment-return', JSON.stringify({userId:1,checkoutId:${JSON.stringify(record.id)},at:Date.now()}))`)
  await command('Page.navigate', { url: origin + '/checkout' })
  await until(`location.search.includes('payment_checkout_id=') && document.body?.innerText.includes('Payment confirmed')`)
  for (const width of [1440, 390, 320]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 768 })
    assert.ok(await evaluate(`document.documentElement.scrollWidth <= innerWidth + 1`))
  }
  record = { ...record, status: 'PENDING', recovery_status: 'RESUMABLE', membership_id: null, can_pay: true }
  await command('Page.navigate', { url: origin + '/checkout?order_id=fitigo_' + record.id.replaceAll('-', '') + '&status=SUCCESS' })
  await until(`document.querySelector('[aria-label="Payment result"]')?.innerText.includes('Payment is not confirmed yet')`)
  assert.equal(await evaluate(`document.body.innerText.includes('Your membership has been activated.')`), false)
  verifyFails = true
  await click('Refresh payment status'); await until(`document.body.innerText.includes('Do not pay again until the original payment is resolved.')`)
  assert.equal(await evaluate(`!!document.querySelector('a[href="/membership/19"]')`), false)
  verifyFails = false
  record = { ...record, status: 'PAID', recovery_status: 'PAID', membership_id: 19, can_pay: false }
  await click('Refresh payment status'); await until(`document.body.innerText.includes('Your membership has been activated.')`)
  assert.equal(await evaluate('window.opens'), 0)
  await command('Page.navigate', { url: origin + '/checkout?payment_checkout_id=invalid&status=SUCCESS' })
  await until(`document.body?.innerText.includes('Payment reference unavailable')`)
  // New session/customer without a previous checkout gets a fresh purchase UI.
  record = null; conflict = false; user.id = 4; user.email = 'other@example.test'
  await command('Page.navigate', { url })
  await until(`${button('Continue to secure payment')} && !${button('Continue to secure payment')}.disabled`)
  assert.equal(await evaluate(`!!${button('Resume original membership')} || !!${button('Resume payment')}`), false)
  assert.deepEqual(errors, [])
  console.log('Membership recovery/return browser PASS: fresh customer, current-payment status, original recovery, safe closure, support, confirmed/legacy/pending/invalid returns, reload, no automatic SDK launch on return, responsive 1440/768/390/320; APIs/SDK mocked.')
} finally { ws.close(); await target.dispose() }