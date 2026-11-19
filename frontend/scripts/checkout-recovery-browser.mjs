// Every API request and SDK invocation is mocked. No gateway or working-data writes.
import assert from 'node:assert/strict'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const replacementFlow = process.env.FITIGO_TEST_REPLACEMENT === '1'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, creates = 0, refreshes = 0, mode = 'expired', recent = true, cartActive = true
let replacementConfirmed = false
const pending = new Map(), errors = []
const base = { id: '11111111-1111-4111-8111-111111111111', kind: 'CART', status: 'PENDING', mode: 'test', amount: '150.00', amount_minor: 15000,
  currency: 'INR', provider: replacementFlow ? 'RAZORPAY' : 'CASHFREE', environment: 'sandbox', gateway_order_id: 'fixture_order', payment_session_id: 'session_fixture', key_id: 'rzp_test_fixture', razorpay_order_id: 'order_fixture',
  booking_ids: [1266], membership_id: null, can_pay: true, can_cancel: false, replacement_safe: false, cart_item_ids: [61],
  payment_expires_at: '2026-11-12T11:16:02Z', items: [{ booking_id: 1266, gym_name: 'Previous checkout gym', booking_date: '2026-11-12', start_time: '18:00:00', quantity: 1, amount: '150.00', currency: 'INR' }] }
let record = { ...base }
const user = { id: 1, first_name: 'Checkout', last_name: 'Fixture', email: 'checkout@example.test' }
function fixture(path, method, body) {
  if (path.endsWith('/auth/session')) return { user, roles: ['CUSTOMER'] }
  if (path.endsWith('/users/me')) return user
  if (path.endsWith('/notifications/inbox')) return { items: [], total: 0, unread_count: 0 }
  if (path.endsWith('/cart/summary')) return { count: cartActive ? 2 : 0, total: cartActive ? '300.00' : '0.00', currency: 'INR' }
  if (path.endsWith('/payments/config')) return { enabled: true, gateway_required: true, mode: 'test', provider: 'RAZORPAY' }
  if (path.endsWith('/payments/quote')) return { total_amount: '300.00', wallet_amount: '0.00', gateway_amount: '300.00', wallet_balance: '0.00', available_wallet_balance: '0.00', reserved_balance: '0.00', wallet_unavailable_reason: 'No available wallet balance.', currency: 'INR', provider: 'RAZORPAY', mode: 'test' }
  if (path.endsWith('/cart/items')) return cartActive ? [62, 63].map(id => ({ id, gym_name: `New cart gym ${id}`, gym_id: 1, booking_date: '2026-11-13', start_time: '18:00:00', member_count: 1, total_price: '150.00', currency: 'INR' })) : []
  if (path.endsWith('/payments/checkouts') && method === 'GET') return recent ? [record] : []
  if (path.endsWith('/payments/checkouts') && method === 'POST') {
    if (replacementFlow && !replacementConfirmed) {
      if (!body.confirm_razorpay_replacement) return { fixtureStatus: 409, detail: { code: 'RAZORPAY_REPLACEMENT_CONFIRMATION_REQUIRED' } }
      replacementConfirmed = true
    }
    creates++; recent = true
    assert.deepEqual(body.cart_item_ids, [62, 63])
    record = { ...base, id: '22222222-2222-4222-8222-222222222222', amount: '300.00', amount_minor: 30000,
      cart_item_ids: [62, 63], booking_ids: [1267, 1268], items: [62, 63].map((id, i) => ({ ...base.items[0], booking_id: 1267 + i, gym_name: `New cart gym ${id}` })) }
    cartActive = false; mode = 'payable'
    return record
  }
  if (path.endsWith('/verify')) { record = { ...record, status: 'PAID', can_pay: false, payment_blocked_reason: 'PAID' }; return record }
  if (/\/bookings\/1267$/.test(path)) return { id: 1267, gym_id: 1, status: 'CONFIRMED', slot_date: '2026-11-13', quantity: 1, total_price: '150.00', currency: 'INR', visitor_names: ['Test Visitor'], access: { status: 'READY', qr_available: false, passes: [] }, payment: { status: 'PAID', amount: '150.00', currency: 'INR', provider: 'CASHFREE' } }
  if (path.endsWith('/gyms/1/details')) return { gym_name: 'New cart gym 62', location: { full_address: 'Fixture address' }, rules: [], facilities: [], images: [] }
  if (path.endsWith('/profile/bookings')) return []
  if (path.endsWith('/refresh')) {
    refreshes++
    if (mode === 'expired') record = { ...record, can_pay: false, payment_blocked_reason: 'BOOKING_EXPIRED' }
    if (mode === 'closed') record = { ...record, can_pay: false, can_cancel: true, replacement_safe: true, payment_blocked_reason: 'BOOKING_EXPIRED' }
    if (mode === 'review') record = { ...record, status: 'REVIEW_REQUIRED', can_pay: false, failure_code: 'FULFILLMENT_UNAVAILABLE', payment_blocked_reason: 'REVIEW_REQUIRED' }
    return record
  }
  if (path.endsWith('/notifications/unread-count')) return { count: 0 }
  if (path.endsWith('/workflow-capabilities')) return {}
  throw Error(`Unexpected API: ${method} ${path}`)
}
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 15000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value }
async function until(expression) { for (let i = 0; i < 250; i++) { if (await evaluate(expression)) return; await new Promise(r => setTimeout(r, 80)) } throw Error(`${expression}: ${await evaluate('document.body.innerText')}; ${errors}`) }
async function click(label, twice = false) { await until(`Array.from(document.querySelectorAll('main button')).some(b=>b.textContent.trim()===${JSON.stringify(label)} && !b.disabled)`); await evaluate(`(()=>{const b=Array.from(document.querySelectorAll('main button')).find(b=>b.textContent.trim()===${JSON.stringify(label)});b.click();${twice ? 'b.click();' : ''}})()`); await new Promise(r => setTimeout(r, 150)) }
ws.onmessage = async event => {
  const m = JSON.parse(event.data), item = pending.get(m.id)
  if (item) { clearTimeout(item.timer); pending.delete(m.id); m.error ? item.reject(Error(m.error.message)) : item.resolve(m.result) }
  if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.text)
  if (m.method !== 'Fetch.requestPaused') return
  const { requestId, request } = m.params
  try {
    if (!new URL(request.url).pathname.startsWith('/api/v1/')) throw Error('Unexpected external gateway request')
    const body = fixture(new URL(request.url).pathname, request.method, request.postData ? JSON.parse(request.postData) : {})
    await command('Fetch.fulfillRequest', { requestId, responseCode: body?.fixtureStatus || 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') })
  } catch (error) { errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
}
try {
  await command('Runtime.enable'); await command('Page.enable')
  await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }, { urlPattern: '*cashfree.com/*' }, { urlPattern: '*razorpay.com/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fitigo:access_token','isolated-checkout-fixture');window.opens=0;window.Cashfree=()=>({checkout:async()=>{window.opens++;return window.paymentSuccess?{paymentDetails:'untrusted'}:{error:{message:'closed'}}}});const interval=window.setInterval;window.setInterval=(fn,ms,...args)=>interval(fn,ms===15000?500:ms,...args)` })
  if (replacementFlow) await command('Page.addScriptToEvaluateOnNewDocument', { source: `window.Razorpay=class{constructor(options){this.options=options}on(){}close(){}open(){window.opens++;if(window.paymentSuccess)this.options.handler({razorpay_order_id:'order_fixture',razorpay_payment_id:'pay_fixture',razorpay_signature:'a'.repeat(64)});else this.options.modal.ondismiss()}}` })
  await command('Page.navigate', { url: origin + '/checkout' })
  await until(`document.body?.innerText.includes('Pay securely')`)
  await evaluate('document.activeElement?.blur()')
  assert.equal(refreshes, 0, 'collapsed history must not reconcile or launch old orders')
  assert.equal(creates, 0); assert.equal(await evaluate('window.opens'), 0)
  assert.equal(await evaluate(`document.body.innerText.includes('Retry / open payment')`), false)
  assert.equal(await evaluate(`document.body.innerText.includes('Cancel unpaid checkout')`), false)
  assert.equal(await evaluate(`document.body.innerText.includes('Resuming a previous checkout')`), false)
  assert.ok(await evaluate(`document.querySelector('.fc-total').innerText.includes('₹300')`))
  assert.equal(await evaluate(`document.querySelector('aside').innerText.includes('Previous checkout gym')`), false)
  assert.equal(await evaluate(`document.querySelector('details').open`), false)
  for (const width of [360, 768, 1440]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 1100, deviceScaleFactor: 1, mobile: width < 640 })
    assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true, `width ${width}`)
  }
  await click('Pay securely', true)
  if (replacementFlow) {
    await until(`document.body.innerText.includes('Start a fresh checkout')`)
    assert.equal(creates, 0); assert.equal(await evaluate('window.opens'), 0)
    assert.equal(await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Start a fresh checkout').disabled`), true)
    assert.ok(await evaluate(`document.body.innerText.includes('not cancelled at the gateway')`))
    await evaluate(`document.querySelector('[aria-label="Replace previous checkout"] input').click()`)
    await click('Start a fresh checkout', true)
  }
  await until(`document.body.innerText.includes('Checkout closed')`)
  assert.equal(creates, 1); assert.equal(await evaluate('window.opens'), 1, 'first payment click must open the matching cart')
  assert.ok(await evaluate(`document.querySelector('.fc-total').innerText.includes('₹300')`))
  assert.ok(await evaluate(`document.querySelector('.fc-content').innerText.includes('New cart gym 62') && document.querySelector('.fc-content').innerText.includes('New cart gym 63')`))
  assert.equal(await evaluate(`document.querySelector('aside').innerText.includes('Previous checkout gym')`), false)
  await click('Continue payment', true)
  await until(`document.body.innerText.includes('Checkout closed')`)
  assert.equal(creates, 1); assert.equal(await evaluate('window.opens'), 2)
  await command('Page.reload')
  await until(`document.body.innerText.includes('Visits in this checkout')`)
  assert.equal(creates, 1); assert.equal(await evaluate('window.opens'), 0)
  mode = 'expired'
  await until(`document.body.innerText.includes('Booking payment window expired')`)
  assert.ok(refreshes > 0)
  assert.equal(await evaluate(`document.body.innerText.includes('Continue payment')`), false)
  mode = 'review'
  await click('Refresh payment status')
  await until(`document.body.innerText.includes('Payment received, but the booking could not be confirmed')`)
  assert.equal(await evaluate(`document.body.innerText.includes('Continue payment')`), false)
  const output = join(tmpdir(), 'fitigo-checkout-redesign'); mkdirSync(output, { recursive: true })
  await evaluate('document.activeElement?.blur()')
  for (const width of [360, 768, 1440]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 1100, deviceScaleFactor: 1, mobile: width < 640 })
    assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true)
    const shot = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
    writeFileSync(join(output, `review-${width}.png`), Buffer.from(shot.data, 'base64'))
  }
  await command('Page.bringToFront')
  await command('Emulation.setFocusEmulationEnabled', { enabled: true })
  await evaluate(`document.querySelector('.fc-details summary').scrollIntoView({block:'center'});document.querySelector('.fc-details summary').focus()`)
  assert.equal(await evaluate(`document.activeElement === document.querySelector('.fc-details summary')`), true)
  await command('Input.dispatchKeyEvent', { type: 'keyDown', key: ' ', code: 'Space', windowsVirtualKeyCode: 32, text: ' ' })
  await command('Input.dispatchKeyEvent', { type: 'keyUp', key: ' ', code: 'Space', windowsVirtualKeyCode: 32 })
  await until(`document.querySelector('.fc-details').open`)
  assert.ok(await evaluate(`document.querySelector('.fc-details').innerText.includes('22222222-2222-4222-8222-222222222222')`))
  // A genuine new-cart click launches immediately; only server verification
  // navigates to confirmation, never the SDK completion alone.
  cartActive = true; recent = false; record = { ...base }; mode = 'payable'
  await command('Page.navigate', { url: origin + '/checkout' })
  await until(`document.body.innerText.includes('Pay securely')`)
  await evaluate('window.paymentSuccess=true')
  await click('Pay securely')
  await until(`location.pathname === '/booking/1267/success' && document.body.innerText.includes('Booking confirmed!')`)
  assert.equal(creates, 2); assert.equal(record.status, 'PAID')
  assert.deepEqual(errors, [])
  console.log('PASS redesigned checkout: first-click gateway, exact cart/total, double-click/reload reuse, review-required/expiry states, keyboard details, 360/768/1440 layout; screenshots:', output)
} finally { ws.close(); await target.dispose() }