// Isolated customer settings, wallet and payment-history fixtures; no real charges.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, balance = '0', profileUpdates = 0, verified = 0, selectedKind = ''
const pending = new Map(), errors = []
const user = { id: 1, first_name: 'Customer', last_name: 'Tester', email: 'customer@example.com', phone: '+919999999999', is_email_verified: true, is_phone_verified: false }
const record = { id: '11111111-1111-4111-8111-111111111111', kind: 'WALLET_TOPUP', provider: 'RAZORPAY', environment: 'sandbox', mode: 'test', status: 'PENDING', amount: '1000.00', amount_minor: 100000, currency: 'INR', key_id: 'rzp_test_fixture', razorpay_order_id: 'order_fixture', gateway_order_id: 'order_fixture', booking_ids: [], membership_id: null, can_pay: true }
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 15000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw Error(result.exceptionDetails.text); return result.result.value }
async function until(expression) { for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await wait(80) } throw Error(`${expression}: ${await evaluate('document.body.innerText')}`) }
async function click(text) { await evaluate(`Array.from(document.querySelectorAll('main button')).find(el=>el.textContent.trim()===${JSON.stringify(text)}).click()`) }
function fixture(path, method, body, query) {
  if (path.endsWith('/auth/session')) return { user, roles: ['CUSTOMER'] }
  if (path.endsWith('/users/me')) {
    if (method === 'PATCH') { profileUpdates++; assert.equal(body.first_name, 'Edited'); return { user: { ...user, first_name: body.first_name }, reauthenticate: false } }
    return user
  }
  if (path.endsWith('/wallet/transactions')) return { balance, currency: 'INR', transactions: [] }
  if (path.endsWith('/payments/config')) return { enabled: true, gateway_required: true, provider: 'RAZORPAY', mode: 'test' }
  if (path.endsWith('/payments/checkouts') && method === 'POST') { assert.equal(body.kind, 'WALLET_TOPUP'); assert.equal(body.amount, '1000.00'); return record }
  if (path.endsWith('/verify')) { verified++; assert.equal(body.razorpay_order_id, 'order_fixture'); balance = '1000.00'; record.status = 'PAID'; record.can_pay = false; return record }
  if (path.endsWith('/payments/history')) {
    selectedKind = query.get('kind') || ''
    return { total: 1, items: [{ id: 'checkout:fixture', source: 'checkout', kind: 'WALLET_TOPUP', status: 'REFUNDED', amount: '1000', currency: 'INR', provider: 'RAZORPAY', mode: 'test', created_at: '2026-10-27T12:00:00+05:30', checkout_id: record.id, provider_order_id: 'order_fixture', transaction_id: 'pay_fixture', failure_code: null, order_details: { requested_amount: '1000' }, bookings: [], membership_ids: [], wallet_entries: [{ id: 1, direction: 'IN', type: 'TOPUP', amount: '1000' }], attempts: [{ transaction_id: 'pay_fixture', status: 'REFUNDED', amount: '1000', refunded_amount: '1000', first_seen_at: '2026-10-27T12:00:00+05:30', updated_at: '2026-10-27T12:05:00+05:30' }] }] }
  }
  if (path.endsWith('/notifications/me')) return []
  throw Error(`Unexpected API ${method} ${path}`)
}
ws.onmessage = async event => {
  const message = JSON.parse(event.data), item = pending.get(message.id)
  if (item) { clearTimeout(item.timer); pending.delete(message.id); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result) }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
  if (message.method === 'Fetch.requestPaused') {
    const { requestId, request } = message.params, url = new URL(request.url)
    try { const data = fixture(url.pathname, request.method, request.postData ? JSON.parse(request.postData) : {}, url.searchParams); await command('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(data)).toString('base64') }) }
    catch (error) { errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
  }
}
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fitigo:access_token','isolated-customer-fixture');window.Razorpay=class{constructor(options){this.options=options}on(){}open(){this.options.handler({razorpay_order_id:'order_fixture',razorpay_payment_id:'pay_fixture',razorpay_signature:'a'.repeat(64)})}}` })
  await command('Page.navigate', { url: `${origin}/wallet/recharge` })
  await until(`document.body.innerText.includes('Review secure recharge')`)
  assert.equal(balance, '0')
  await click('Review secure recharge'); await click('Continue to secure payment')
  await until(`document.body.innerText.includes('wallet credited')`)
  assert.equal(verified, 1); assert.equal(balance, '1000.00')
  await command('Page.navigate', { url: `${origin}/profile/payments` })
  await until(`document.body.innerText.includes('Transaction and order details')`)
  await evaluate(`document.querySelector('main summary').click()`)
  assert.ok(await evaluate(`document.body.innerText.includes('pay_fixture') && document.body.innerText.includes('order_fixture') && document.body.innerText.includes('Refunded')`))
  await evaluate(`(() => {const el=document.querySelector('main select');el.value='WALLET_TOPUP';el.dispatchEvent(new Event('change',{bubbles:true}))})()`)
  await until(`document.body.innerText.includes('Transaction and order details')`); assert.equal(selectedKind, 'WALLET_TOPUP')
  for (const width of [360, 768, 1440]) { await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 640 }); await wait(80); assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true) }
  await command('Page.navigate', { url: `${origin}/settings` })
  await until(`document.body.innerText.includes('Edit profile') && document.querySelector('form[aria-label="Change password"]') !== null`)
  await evaluate(`(() => {const el=document.querySelector('input[name="first_name"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'Edited');el.dispatchEvent(new Event('input',{bubbles:true}))})()`)
  await click('Save profile'); await until(`document.body.innerText.includes('Profile saved')`); assert.equal(profileUpdates, 1)
  for (const width of [360, 768, 1440]) { await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 640 }); await wait(80); assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true) }
  assert.deepEqual(errors, [])
  console.log('PASS customer wallet gateway confirmation, payment history IDs/refunds/filtering, profile save, password form and responsive layout')
} finally { ws.close(); await target.dispose() }