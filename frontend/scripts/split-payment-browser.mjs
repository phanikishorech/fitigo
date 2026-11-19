// Isolated browser context; intercept every API/SDK call. Never reaches payment providers.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, balance = 40, provider = 'RAZORPAY', creates = 0, record = null, quoteDelay = 0
const pending = new Map(), errors = [], user = { id: 1, first_name: 'Wallet', last_name: 'Fixture', email: 'wallet@example.test' }
function amounts(body) { const wallet = body.use_wallet ? Math.min(Number(body.wallet_amount ?? balance), balance, 150) : 0; return { total_amount: '150.00', wallet_amount: wallet.toFixed(2), gateway_amount: (150 - wallet).toFixed(2) } }
function fixture(path, method, body) {
  if (path.endsWith('/auth/session')) return { user, roles: ['CUSTOMER'] }
  if (path.endsWith('/users/me')) return user
  if (path.endsWith('/cart/summary')) return { count: 1, total: '150.00', currency: 'INR' }
  if (path.endsWith('/payments/config')) return { enabled: true, gateway_required: true, mode: 'test', provider }
  if (path.endsWith('/cart/items')) return [{ id: 1, gym_id: 1, gym_name: 'Wallet fixture gym', booking_date: '2026-12-01', start_time: '18:00:00', member_count: 1, total_price: '150.00', currency: 'INR' }]
  if (path.endsWith('/payments/quote')) return { ...amounts(body), wallet_balance: balance.toFixed(2), available_wallet_balance: balance.toFixed(2), reserved_balance: '0.00', wallet_unavailable_reason: balance ? null : 'No available wallet balance.', provider, currency: 'INR', mode: 'test' }
  if (path.endsWith('/payments/checkouts') && method === 'GET') return []
  if (path.endsWith('/payments/checkouts') && method === 'POST') {
    creates++; const allocation = amounts(body), walletOnly = Number(allocation.gateway_amount) === 0
    record = { ...allocation, amount: allocation.gateway_amount, amount_minor: Math.round(Number(allocation.gateway_amount) * 100),
      id: '11111111-1111-4111-8111-111111111111', kind: 'CART', status: walletOnly ? 'PAID' : 'PENDING', wallet_status: walletOnly ? 'DEBITED' : 'HELD',
      currency: 'INR', mode: 'test', provider, environment: 'sandbox', key_id: 'rzp_test_fixture', razorpay_order_id: walletOnly ? null : 'order_fixture',
      gateway_order_id: walletOnly ? null : 'order_fixture', payment_session_id: walletOnly ? null : 'session_fixture', booking_ids: [], membership_id: null,
      cart_item_ids: [1], can_pay: !walletOnly, can_cancel: false, failure_code: null }
    return record
  }
  if (path.endsWith('/refresh')) return record
  if (path.endsWith('/verify')) return { ...record, status: 'PAID', can_pay: false, wallet_status: 'DEBITED' }
  if (path.includes('/notifications')) return path.endsWith('/unread-count') ? { count: 0 } : { items: [], total: 0, unread_count: 0 }
  throw Error(`Unexpected API ${method} ${path}`)
}
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 15000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text); return result.result.value }
async function until(expression) { for (let i = 0; i < 150; i++) { if (await evaluate(expression)) return; await new Promise(resolve => setTimeout(resolve, 100)) } throw Error(`${expression}: ${await evaluate('document.body.innerText')}; ${errors}`) }
const section = `document.querySelector('[aria-label="Payment method"]')`
const pay = `Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Pay securely')`
ws.onmessage = async event => {
  const message = JSON.parse(event.data), item = pending.get(message.id)
  if (item) { clearTimeout(item.timer); pending.delete(message.id); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result) }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
  if (message.method !== 'Fetch.requestPaused') return
  const { requestId, request } = message.params
  try {
    const path = new URL(request.url).pathname
    if (!path.startsWith('/api/v1/')) throw Error('Unexpected external gateway request')
    const body = fixture(path, request.method, request.postData ? JSON.parse(request.postData) : {})
    if (path.endsWith('/payments/quote') && quoteDelay) await new Promise(resolve => setTimeout(resolve, quoteDelay))
    await command('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') })
  } catch (error) {
    // Navigation can cancel a paused request before the fixture responds.
    if (error.message.includes('Invalid InterceptionId')) return
    errors.push(error.message)
    await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }).catch(() => {})
  }
}
try {
  await command('Runtime.enable'); await command('Page.enable')
  await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }, { urlPattern: '*cashfree.com/*' }, { urlPattern: '*razorpay.com/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fitigo:access_token','wallet-fixture');window.opens=0;window.online=null;window.Razorpay=class{constructor(o){this.o=o}on(){}open(){window.opens++;window.online=this.o.amount;this.o.modal.ondismiss()}};window.Cashfree=()=>({checkout:async(o)=>{window.opens++;window.session=o.paymentSessionId;return {error:{message:'closed'}}}})` })
  for (const configured of ['RAZORPAY', 'CASHFREE']) {
    provider = configured; balance = 40; record = null
    await command('Page.navigate', { url: origin + '/checkout' })
    await until(`${pay} && !${pay}.disabled`)
    assert.equal(await evaluate(`${section}.querySelector('input[type=checkbox]').checked`), false)
    await evaluate(`${section}.querySelector('input[type=checkbox]').click()`)
    await until(`${section}.innerText.includes('₹110') && !${pay}.disabled`)
    for (const width of [320, 390, 768, 1440]) {
      await command('Emulation.setDeviceMetricsOverride', { width, height: 1100, deviceScaleFactor: 1, mobile: width < 640 })
      assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true, `overflow ${width}`)
    }
    // Lower contribution is a server quote, not a client-created gateway amount.
    await evaluate(`(()=>{const input=${section}.querySelector('input[type=number]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'20');input.dispatchEvent(new Event('input',{bubbles:true}))})()`)
    await until(`${section}.innerText.includes('₹130') && !${pay}.disabled`)
    await evaluate(`${pay}.click()`)
    await until('window.opens===1')
    assert.equal(record.gateway_amount, '130.00')
    if (provider === 'RAZORPAY') assert.equal(await evaluate('window.online'), 13000)
    else assert.equal(await evaluate('window.session'), 'session_fixture')
  }
  for (const value of [0, 150, 200]) {
    balance = value; record = null
    await command('Page.navigate', { url: origin + '/checkout' }); await until(`${pay} && !${pay}.disabled`)
    if (!value) {
      assert.equal(await evaluate(`${section}.querySelector('input[type=checkbox]').disabled`), true)
      assert.ok(await evaluate(`${section}.innerText.includes('No available wallet balance')`)); continue
    }
    await evaluate(`${section}.querySelector('input[type=checkbox]').click()`)
    await until(`${section}.innerText.includes('Wallet-only') && !${pay}.disabled`)
    const before = creates
    await evaluate(`${pay}.click()`)
    for (let attempt = 0; attempt < 50 && creates === before; attempt++) await new Promise(resolve => setTimeout(resolve, 100))
    assert.equal(creates, before + 1)
    assert.equal(await evaluate('window.opens'), 0)
    assert.equal(record.wallet_amount, '150.00'); assert.equal(record.gateway_amount, '0.00')
  }
  assert.deepEqual(errors, [])
  console.log('Split-payment browser PASS: both provider remainders, custom amount, zero balance, wallet-only, responsive widths; all APIs/SDKs mocked.')
} finally { ws.close(); await target.dispose() }