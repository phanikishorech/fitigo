// Isolated reporting/cancellation HTTP fixtures; no real accounts or mutations.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const target = await isolatedBrowserTarget()
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, mode = 'test', cancelled = false, cancellations = 0
const pending = new Map(), errors = []
const user = { id: 1, first_name: 'Fixture', last_name: 'Admin', email: 'admin@example.com', status: 'ACTIVE', phone: null }
const booking = { id: 1, status: 'CONFIRMED', slot_date: '2026-10-26', quantity: 1, total_price: '100', currency: 'INR', customer: { ...user, id: 3 }, gym: { id: 1, name: 'Fixture gym', owner_user_id: 2, status: 'APPROVED', is_active: true }, slot: { id: 1, name: 'Visit', start_time: '10:00', end_time: '11:00' }, payment: { id: 1, provider: 'CASHFREE', status: 'PAID', amount: '100', currency: 'INR' } }
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw Error(result.exceptionDetails.text); return result.result.value }
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until(expression) { for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await wait(80) } throw Error('Not ready: '+expression+'; '+await evaluate('document.body.innerText')) }
async function visit(path) { await command('Page.navigate', { url: origin+path }); await wait(150) }
ws.onmessage = async event => {
  const m = JSON.parse(event.data)
  if (pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(Error(m.error.message)) : p.resolve(m.result) }
  if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.text)
  if (m.method !== 'Fetch.requestPaused') return
  const { requestId, request } = m.params, path = new URL(request.url).pathname
  try {
    let body
    if (path.endsWith('/auth/session')) body = { user, roles: ['ADMIN'] }
    else if (path.endsWith('/users/me')) body = user
    else if (path.endsWith('/users/me/roles')) body = ['ADMIN']
    else if (path.endsWith('/admin/dashboard/summary')) body = { users: { total: 3, in_period: 0 }, gyms: { total: 1, in_period: 0, pending_approval: 0 }, bookings: { in_period: 1, confirmed_in_period: 1 }, revenue: { in_period: '100', currency: 'INR', mode } }
    else if (path.endsWith('/admin/reports/bookings/daily')) body = [{ day: '2026-10-26', total_bookings: 1, confirmed_bookings: 1, cancelled_bookings: 0, expired_bookings: 0, paid_amount_total: '100', mode }]
    else if (path.endsWith('/admin/gyms') || path.endsWith('/admin/bookings')) body = []
    else if (path.endsWith('/admin/bookings/1/cancel')) { cancellations++; cancelled = true; body = { status: 'ok', new_status: 'CANCELLED', refund_initiated: false } }
    else if (path.endsWith('/admin/bookings/1')) body = { ...booking, status: cancelled ? 'CANCELLED' : 'CONFIRMED' }
    else throw Error('Unexpected API '+path)
    await command('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') })
  } catch (error) { errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
}
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: "localStorage.setItem('fitigo:access_token','isolated-financial-fixture')" })
  for (const value of ['test', 'live']) {
    mode = value
    for (const path of ['/admin/dashboard', '/admin/reports']) {
      await visit(path); await until(`document.body.innerText.includes(${JSON.stringify(value === 'test' ? 'Test scope' : 'Live scope')})`)
      for (const width of [360, 768, 1440]) { await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 640 }); assert.equal(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'), true) }
    }
  }
  await visit('/admin/bookings/1'); await until(`document.body.innerText.includes('Force Cancel Booking')`)
  assert.equal(await evaluate(`document.body.innerText.includes('Cancellation does not initiate a gateway refund or wallet credit')`), true)
  await evaluate(`Array.from(document.querySelectorAll('button')).find(el=>el.textContent.trim()==='Force Cancel Booking').click()`)
  await until(`!!document.querySelector('dialog[open]')`)
  assert.equal(await evaluate(`document.querySelector('dialog').innerText.includes('does not initiate a gateway refund')`), true)
  await evaluate(`Array.from(document.querySelectorAll('dialog button')).find(el=>el.textContent.trim()==='Force Cancel').click()`)
  await until(`document.body.innerText.includes('Cancellation request completed')`)
  assert.equal(cancellations, 1)
  assert.equal(await evaluate(`document.querySelector('main').innerText.includes('Paid')`), true)
  assert.equal(await evaluate(`document.querySelector('main').innerText.includes('Refunded')`), false)
  assert.deepEqual(errors, [])
  console.log('PASS admin test/live labels, dashboard/daily scope, responsive layouts, cancellation warning and paid-not-refunded state')
} finally { await command('Fetch.disable').catch(() => {}); ws.close(); await target.dispose() }