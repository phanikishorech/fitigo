// Isolated browser checkout fixtures. No real Razorpay requests or database writes.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const provider = process.env.FITIGO_TEST_PROVIDER === 'cashfree' ? 'CASHFREE' : 'RAZORPAY'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, record = null, creations = 0, verifies = 0, interrupted = false, recover = false
const pending = new Map(), errors = []
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 15000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw Error(result.exceptionDetails.text); return result.result.value }
async function until(expression) { for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await wait(70) } throw Error(`${expression}; ${await evaluate('document.body.innerText')}; ${errors}`) }
async function click(text) { await evaluate(`Array.from(document.querySelectorAll('main button')).find(el=>el.textContent.trim()===${JSON.stringify(text)}).click()`); await wait(100) }
const user = { id: 1, first_name: 'Payment', last_name: 'Tester', email: 'payment@example.test' }
function fixture(path, method, body) {
  if (path.endsWith('/auth/session')) return { user, roles: ['CUSTOMER'] }
  if (path.endsWith('/users/me')) return user
  if (path.endsWith('/payments/config')) return { enabled: true, gateway_required: true, mode: 'test', provider }
  if (path.endsWith('/cart/items')) return []
  if (path.endsWith('/payments/checkouts') && method === 'GET') return record ? [record] : []
  if (path.endsWith('/payments/checkouts') && method === 'POST') {
    creations++
    assert.equal(body.kind, 'SINGLE_GYM'); assert.equal(body.plan_id, 1); assert.equal('amount' in body, false)
    record = { id: '11111111-1111-4111-8111-111111111111', kind: 'SINGLE_GYM', status: 'PENDING', mode: 'test', amount: '500', amount_minor: 50000,
      currency: 'INR', key_id: 'rzp_test_fixture', razorpay_order_id: 'order_fixture', booking_ids: [], membership_id: null, can_pay: true,
      provider, environment: 'sandbox', payment_session_id: 'session_fixture' }
    return record
  }
  if (path.endsWith('/verify')) {
    verifies++
    if (provider === 'CASHFREE') assert.deepEqual(body, {})
    else assert.equal(body.razorpay_order_id, 'order_fixture')
    if (interrupted) throw Error('INTERRUPTED')
    record.status = 'PAID'; record.can_pay = false; return record
  }
  if (path.endsWith('/refresh')) {
    if (recover) { record.status = 'PAID'; record.can_pay = false }
    return record
  }
  if (path.includes('/payments/checkouts/')) return record
  if (path.endsWith('/memberships/gyms/1/plans')) return [{ id: 1, gym_id: 1, name: 'Single gym plan', duration_days: 30, price: '500', currency: 'INR', is_active: true }]
  if (path.endsWith('/wallet-quote')) return { plan: { name: 'Single gym plan', duration_value: 30, final_price: '500', currency: 'INR' }, quote_token: 'a'.repeat(64), payment_mode: provider, payment_available: true }
  if (path.includes('/gyms/1')) return { gym_name: 'Test Gym', location: { full_address: 'Fixture address' }, images: [], facilities: [], rules: [] }
  if (path.endsWith('/notifications/me')) return []
  throw Error(`Unexpected API ${path}`)
}
ws.onmessage = async event => {
  const message = JSON.parse(event.data), item = pending.get(message.id)
  if (item) { clearTimeout(item.timer); pending.delete(message.id); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result) }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
  if (message.method === 'Fetch.requestPaused') {
    const { requestId, request } = message.params
    try {
      const body = fixture(new URL(request.url).pathname, request.method, request.postData ? JSON.parse(request.postData) : {})
      await command('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') })
    } catch (error) { if (error.message !== 'INTERRUPTED') errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
  }
}
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fitigo:access_token','isolated-payment-fixture');window.paymentOutcome='cancel';window.Razorpay=class{constructor(options){this.options=options;window.checkoutOptions=options}on(event,fn){this.failed=fn}close(){}open(){if(window.paymentOutcome==='cancel')this.options.modal.ondismiss();else if(window.paymentOutcome==='fail')this.failed();else this.options.handler({razorpay_order_id:'order_fixture',razorpay_payment_id:'pay_fixture',razorpay_signature:'a'.repeat(64)})}}` })
  if (provider === 'CASHFREE') await command('Page.addScriptToEvaluateOnNewDocument', { source: `window.Cashfree=options=>{window.cashfreeMode=options.mode;return {checkout:async input=>{window.checkoutOptions=input;return window.paymentOutcome==='success'?{paymentDetails:'not proof'}:{error:{message:'closed or failed'}}}}}` })
  await command('Page.navigate', { url: `${origin}/membership/checkout?gymId=1&planId=1` })
  await until(`document.body.innerText.includes('Continue to secure payment')`)
  await click('Continue to secure payment')
  await until(`document.body.innerText.includes('Checkout closed')`)
  assert.equal(verifies, 0); assert.equal(creations, 1)
  if (provider === 'CASHFREE') {
    assert.equal(await evaluate('window.checkoutOptions.paymentSessionId'), 'session_fixture')
    assert.equal(await evaluate('window.cashfreeMode'), 'sandbox')
  } else assert.equal(await evaluate('window.checkoutOptions.amount'), 50000)
  await evaluate(`window.paymentOutcome='fail'`); await click('Retry / open payment')
  await until(`document.body.innerText.includes('${provider === 'CASHFREE' ? 'Checkout closed' : 'Payment failed'}')`)
  assert.equal(creations, 1); assert.equal(verifies, 0)
  interrupted = true
  await evaluate(`window.paymentOutcome='success'`); await click('Retry / open payment')
  await until(`document.body.innerText.includes('verification was interrupted')`)
  assert.equal(record.status, 'PENDING'); assert.equal(verifies, 1)
  interrupted = false; recover = true
  await click('Refresh payment status'); await until(`document.body.innerText.includes('Payment confirmed by FitiGo')`)
  assert.equal(creations, 1)
  for (const width of [360, 768, 1440]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 640 }); await wait(80)
    assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true)
  }
  await command('Page.navigate', { url: `${origin}/checkout` })
  await until(`document.body.innerText.includes('Recent payments')`)
  assert.ok(await evaluate(`document.body.innerText.includes('TEST MODE')`))
  assert.deepEqual(errors, [])
  console.log(`PASS ${provider} existing membership/checkout UI: Test Mode, dismissal, failure, retry reuse, interrupted callback, refresh recovery, recent payments, responsive layout`)
} finally { ws.close(); await target.dispose() }