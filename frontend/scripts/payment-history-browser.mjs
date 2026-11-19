// Network-isolated customer payment-history UI. No working data or gateway requests.
import assert from 'node:assert/strict'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let seq = 0, mode = 'data', refreshes = 0, cancels = 0, delayRefresh = false, failRefresh = false
const pending = new Map(), errors = [], historyRequests = []
const user = { id: 1, first_name: 'History', last_name: 'Fixture', email: 'history@example.test' }
const at = '2026-11-12T19:05:00+05:30'
const rows = [
  ['CART', 'PAID', '150.00', 'RAZORPAY', 'test'],
  ['MULTI_GYM', 'PAID', '2199.00', 'RAZORPAY', 'test'],
  ['WALLET_TOPUP', 'PENDING', '500.00', 'CASHFREE', 'live'],
  ['BOOKING', 'REVIEW_REQUIRED', '100.00', 'CASHFREE', 'test'],
  ['SINGLE_GYM', 'PARTIALLY_REFUNDED', '1000.00', 'RAZORPAY', 'live'],
  ['CART', 'SUPERSEDED', '150.00', 'RAZORPAY', 'test'],
  ['BOOKING', 'FAILED', '250.00', 'RAZORPAY', null]
].map(([kind, status, amount, provider, mode], i) => ({ id: `checkout:fixture-${i}`, source: 'checkout', kind, status, amount, currency: 'INR', provider, mode,
  created_at: at, updated_at: at, checkout_id: mode === null ? null : `fixture-${i}`, provider_order_id: `order_${'x'.repeat(70)}${i}`, transaction_id: status === 'PAID' ? `pay_${'y'.repeat(70)}${i}` : null,
  failure_code: status === 'REVIEW_REQUIRED' ? 'FULFILLMENT_UNAVAILABLE' : null,
  order_details: kind === 'MULTI_GYM' ? { name: 'All-access monthly membership', duration_value: 1, duration_unit: 'MONTH' } : null,
  bookings: i === 0 ? [{ id: 1270, date: '2026-11-12', status: 'CONFIRMED', amount: '150.00', quantity: 1, currency: 'INR' }] : [],
  membership_ids: i === 1 ? [10] : [], wallet_entries: i === 2 ? [{ id: 4, direction: 'IN', type: 'TOPUP', amount: '500.00' }] : [],
  attempts: i === 0 || i === 4 ? [{ transaction_id: `pay_${'z'.repeat(80)}${i}`, status: i === 4 ? 'PARTIALLY_REFUNDED' : 'SUCCESS', amount, currency: 'INR', refunded_amount: i === 4 ? '100.00' : '0.00', first_seen_at: at, updated_at: at }] : [] }))
function checkout(id) { const row = rows.find(r => r.checkout_id === id); return { id, kind: row.kind, status: row.status, mode: row.mode, amount: row.amount, amount_minor: Number(row.amount)*100, currency: 'INR', provider: row.provider,
  environment: row.mode === 'test' ? 'sandbox' : 'production', booking_ids: row.bookings.map(b => b.id), membership_id: row.membership_ids[0] || null,
  can_pay: false, can_cancel: row.status === 'PENDING', replacement_safe: false, failure_code: row.failure_code } }
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++seq, timer = setTimeout(() => reject(Error(method)), 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value }
async function until(expression) { for (let i = 0; i < 250; i++) { if (await evaluate(expression)) return; await new Promise(r => setTimeout(r, 60)) } throw Error(JSON.stringify({ expression, body: await evaluate('document.body.innerText'), errors })) }
async function click(label, selector = 'main button') { await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(b=>b.textContent.trim()===${JSON.stringify(label)}).click()`); await new Promise(r => setTimeout(r, 100)) }
async function filter(index, value) { await evaluate(`(()=>{const el=document.querySelectorAll('.ph-filters select')[${index}];el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change',{bubbles:true}));})()`); await new Promise(r => setTimeout(r, 120)) }
ws.onmessage = async event => {
  const m = JSON.parse(event.data), item = pending.get(m.id)
  if (item) { clearTimeout(item.timer); pending.delete(m.id); m.error ? item.reject(Error(m.error.message)) : item.resolve(m.result) }
  if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.text)
  if (m.method !== 'Fetch.requestPaused') return
  const { requestId, request } = m.params, url = new URL(request.url), path = url.pathname
  try {
    let body, responseCode = 200
    if (path.endsWith('/auth/session')) body = { user, roles: ['CUSTOMER'] }
    else if (path.endsWith('/notifications/inbox')) body = { items: [], total: 0, unread_count: 0 }
    else if (path.endsWith('/cart/summary')) body = { count: 0, total: '0.00', currency: 'INR' }
    else if (path.endsWith('/users/me')) body = user
    else if (path.endsWith('/payments/history')) {
      assert.equal(request.method, 'GET'); historyRequests.push(Object.fromEntries(url.searchParams))
      let items = rows.filter(r => (!url.searchParams.get('kind') || r.kind === url.searchParams.get('kind')) && (!url.searchParams.get('status') || r.status === url.searchParams.get('status')))
      if (mode === 'empty') items = []
      body = { items: url.searchParams.get('offset') === '20' ? [rows[1]] : items, total: mode === 'pages' ? 21 : items.length }
      if (mode === 'error') { responseCode = 500; body = { detail: 'private SQL traceback' } }
    } else if (path.endsWith('/refresh')) {
      assert.equal(request.method, 'POST'); refreshes++
      if (delayRefresh) await new Promise(r => setTimeout(r, 500))
      body = checkout(path.split('/').at(-2))
      if (failRefresh) { responseCode = 503; body = { detail: 'private SQL traceback' } }
    } else if (path.endsWith('/cancel')) {
      assert.equal(request.method, 'POST'); cancels++
      const id = path.split('/').at(-2); rows.find(r => r.checkout_id === id).status = 'CANCELLED'; body = { ...checkout(id), can_cancel: false, replacement_safe: true }
    } else throw Error(`Unexpected request: ${request.method} ${request.url}`)
    await command('Fetch.fulfillRequest', { requestId, responseCode, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') })
  } catch (error) { if (!/Invalid InterceptionId/.test(error.message)) errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }).catch(() => {}) }
}
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }, { urlPattern: '*razorpay.com/*' }, { urlPattern: '*cashfree.com/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fitigo:access_token','isolated-history-fixture')` })
  await command('Page.navigate', { url: origin + '/profile/payments' })
  await until(`document.querySelectorAll('.ph-card').length===7`)
  assert.equal(refreshes, 0); assert.equal(cancels, 0)
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('.ph-details')).every(d=>!d.open)`), true)
  assert.ok(await evaluate(`document.body.innerText.includes('Multi-gym membership') && document.body.innerText.includes('Test · no real money') && document.body.innerText.includes('Live payment') && document.body.innerText.includes('Mode not recorded')`))
  assert.ok(await evaluate(`document.body.innerText.includes('Payment received, but the purchase could not be confirmed') && document.body.innerText.includes('not cancelled at the gateway')`))
  assert.equal(await evaluate(`document.body.innerText.includes('pay_yyyy')`), false)
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('.ph-page')).fontFamily===getComputedStyle(document.querySelector('.fg-app')).fontFamily`), true)
  assert.equal(await evaluate(`document.querySelectorAll('.ph-card')[6].querySelector('button')===null`), true)
  const output = join(tmpdir(), 'fitigo-payment-history'); mkdirSync(output, { recursive: true })
  for (const width of [360, 768, 1440]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 1050, deviceScaleFactor: 1, mobile: width < 640 })
    await evaluate('document.activeElement?.blur()')
    assert.equal(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'), true, `collapsed ${width}`)
    const shot = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }); writeFileSync(join(output, `history-${width}.png`), Buffer.from(shot.data, 'base64'))
    await evaluate(`document.querySelector('.ph-details').open=true`)
    assert.equal(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'), true, `expanded ${width}`)
    assert.ok(await evaluate(`document.querySelector('.ph-details').innerText.includes('pay_yyyy') && document.querySelector('.ph-details').innerText.includes('Refunded amount')`))
    await evaluate(`document.querySelector('.ph-details').open=false`)
  }
  await command('Page.bringToFront'); await command('Emulation.setFocusEmulationEnabled', { enabled: true })
  await evaluate(`document.querySelector('.ph-details summary').focus()`)
  await command('Input.dispatchKeyEvent', { type: 'keyDown', key: ' ', code: 'Space', windowsVirtualKeyCode: 32, text: ' ' })
  await command('Input.dispatchKeyEvent', { type: 'keyUp', key: ' ', code: 'Space', windowsVirtualKeyCode: 32 })
  await until(`document.querySelector('.ph-details').open`)
  assert.ok(await evaluate(`!!document.querySelector('.ph-details a[href="/bookings/1270"]')`))
  const shot = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }); writeFileSync(join(output, 'history-expanded.png'), Buffer.from(shot.data, 'base64'))
  await click('Check payment status')
  await until(`!!document.querySelector('dialog[open]') && document.querySelector('dialog').innerText.includes('Payment confirmed')`)
  assert.equal(refreshes, 1)
  assert.equal(await evaluate(`document.querySelector('dialog').innerText.includes('Continue payment')`), false)
  await evaluate(`document.querySelector('dialog button[aria-label="Close dialog"]').click()`)
  await until(`document.querySelectorAll('.ph-card').length===7`)
  await filter(0, 'WALLET_TOPUP'); await until(`document.querySelectorAll('.ph-card').length===1`)
  assert.equal(historyRequests.at(-1).kind, 'WALLET_TOPUP'); assert.equal(historyRequests.at(-1).offset, '0')
  await click('Manage payment'); await until(`document.querySelector('dialog')?.innerText.includes('Cancel unpaid checkout')`)
  await click('Cancel unpaid checkout', 'dialog button'); await until(`document.querySelector('dialog')?.innerText.includes('Checkout closed')`)
  assert.equal(cancels, 1)
  await evaluate(`document.querySelector('dialog button[aria-label="Close dialog"]').click()`)
  await click('Clear filters'); await filter(1, 'SUPERSEDED'); await until(`document.querySelectorAll('.ph-card').length===1`)
  assert.equal(historyRequests.at(-1).status, 'SUPERSEDED')
  await click('Clear filters'); mode = 'pages'; await click('Refresh list'); await until(`document.body.innerText.includes('of 21')`)
  await click('Next'); await until(`document.body.innerText.includes('Page 2')`); assert.equal(historyRequests.at(-1).offset, '20')
  await filter(0, 'MULTI_GYM'); await until(`document.body.innerText.includes('Page 1')`); assert.equal(historyRequests.at(-1).offset, '0')
  mode = 'empty'; await click('Refresh list'); await until(`document.body.innerText.includes('No matching payments')`)
  await click('Clear filters'); await until(`document.body.innerText.includes('Your payment history starts here')`)
  mode = 'error'; await click('Refresh list'); await until(`document.body.innerText.includes('Something went wrong')`)
  assert.equal(await evaluate(`document.body.innerText.includes('private SQL')`), false)
  mode = 'data'; await click('Try again'); await until(`document.querySelectorAll('.ph-card').length===7`)
  failRefresh = true; await click('Check payment status'); await until(`!!document.querySelector('dialog .fg-alert')`)
  assert.equal(await evaluate(`document.body.innerText.includes('private SQL')`), false)
  await evaluate(`document.querySelector('dialog button[aria-label="Close dialog"]').click()`); failRefresh = false
  await until(`document.querySelectorAll('.ph-card').length===7`)
  delayRefresh = true; await click('Check payment status'); await until(`document.querySelector('dialog')?.innerText.includes('Checking the original')`)
  await evaluate(`document.querySelector('dialog button[aria-label="Close dialog"]').click()`)
  await new Promise(r => setTimeout(r, 650)); assert.equal(await evaluate(`!!document.querySelector('dialog[open]')`), false)
  assert.deepEqual(errors, [])
  console.log('PASS history redesign: preserved font/theme, details/currency/status/modes, filters/pagination, guarded actions, close-in-flight, keyboard, empty/error and 360/768/1440. Artifacts:', output)
} finally { ws.close(); await target.dispose() }