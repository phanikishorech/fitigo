// Isolated browser/API fixtures; never requests application business data.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, fail = false
const pending = new Map(), errors = [], calls = []
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 15000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw Error(result.exceptionDetails.text); return result.result.value }
async function until(expression) { for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await wait(80) } throw Error(`${expression}: ${await evaluate('document.body.innerText')}`) }
const gyms = [1, 2].map(id => ({ id, name: `Analytics Gym ${id}`, city: 'City', status: 'APPROVED', is_active: true }))
function fixture(path, query) {
  if (path.endsWith('/auth/session')) return { user: { id: 1, first_name: 'Owner', email: 'owner@example.test' }, roles: ['GYM_OWNER'] }
  if (path.endsWith('/gym-owner/gyms')) return gyms
  const gym = query.get('gym_id'), empty = query.get('date_from') === '2026-10-01', count = empty ? 0 : gym ? Number(gym) : 3
  if (path.endsWith('/analytics')) {
    const summary = { generated_at: '2026-10-27T12:00:00+05:30', upcoming_visits: count, visits: { total: count * 3, fitigo_member: count, single_gym_membership: count, individual_booking: count },
      bookings: { in_period: count * 4 }, attendance: { upcoming: count, attended: count, cancelled: count, no_show: count, pending_payment: 0, expired: 0, unresolved: 0 },
      revenue: { mode: 'test', total: String(count * 100), single_gym_membership: String(count * 60), individual_booking: String(count * 40), fully_refunded_sales: '0', partial_refund_count: 0, excluded_paid_records: 0 } }
    return { summary, grouping: 'daily', series: [{ date: query.get('date_from'), date_to: query.get('date_from'), visits: count * 3, revenue: String(count * 100) }], revenue_by_gym: empty ? [] : [{ gym_id: 1, gym_name: 'Analytics Gym 1', total: '100', single_gym_membership: '60', individual_booking: '40' }] }
  }
  const offset = Number(query.get('offset') || 0), id = offset + 1
  if (path.endsWith('/analytics/bookings')) return { total: empty ? 0 : 12, items: empty ? [] : [{ id, gym_name: `Analytics Gym ${gym || 1}`, date: query.get('date_from'), start_time: '15:00:00', slot_name: 'Gym visit', customer: 'Visitor', visitors: ['Guest'], access_source: 'BOOKING_ACCESS', quantity: 1, amount: '100', currency: 'INR', status: 'CONFIRMED', category: query.get('category') || 'upcoming', payment_status: 'PAID' }] }
  if (path.endsWith('/analytics/transactions')) return { total: empty ? 0 : 12, items: empty ? [] : [{ id: `payment:${id}`, record_id: id, gym_name: `Analytics Gym ${gym || 1}`, category: 'individual_booking', recorded_at: '2026-10-27T12:00:00+05:30', provider: 'RAZORPAY', mode: 'live', payment_status: query.get('payment_status') || 'PAID', checkout_status: 'PAID', amount: '100', recognized_amount: '100', included: true, booking_id: id, transaction_id: `pay_${id}` }] }
  if (path.endsWith('/analytics/attendance')) return { total: empty ? 0 : 1, items: empty ? [] : [{ id: 1, gym_name: `Analytics Gym ${gym || 1}`, customer: 'Checked-in Guest', category: 'individual_booking', recorded_at: '2026-10-27T12:00:00+05:30', booking_id: 1 }] }
  throw Error(`Unexpected API ${path}`)
}
ws.onmessage = async event => {
  const message = JSON.parse(event.data), item = pending.get(message.id)
  if (item) { clearTimeout(item.timer); pending.delete(message.id); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result) }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
  if (message.method === 'Fetch.requestPaused') {
    const { requestId, request } = message.params, url = new URL(request.url); calls.push(url.pathname + url.search)
    try { const data = fixture(url.pathname, url.searchParams); await command('Fetch.fulfillRequest', { requestId, responseCode: fail && url.pathname.endsWith('/analytics') ? 500 : 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(data)).toString('base64') }) }
    catch (error) { errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
  }
}
async function select(label, value) { await evaluate(`(() => {const el=Array.from(document.querySelectorAll('label')).find(el=>el.textContent.startsWith(${JSON.stringify(label)})).querySelector('select');el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change',{bubbles:true}))})()`) }
async function button(text) { await evaluate(`Array.from(document.querySelectorAll('main button')).find(el=>el.textContent.trim()===${JSON.stringify(text)}).click()`) }
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: "localStorage.setItem('fitigo:access_token','isolated-analytics-fixture')" })
  await command('Page.navigate', { url: `${origin}/owner/analytics?date_from=2026-10-27&date_to=2026-10-27&gym_id=all` })
  await until(`document.querySelectorAll('.ow-chart svg').length===2 && document.body.innerText.includes('Checked-in Guest')`)
  for (const text of ['Visits Over Time', 'Booking outcomes', 'Revenue Over Time', 'Payment records', 'Revenue by gym']) assert.ok(await evaluate(`document.body.innerText.includes(${JSON.stringify(text)})`))
  await evaluate(`document.querySelector('.ow-chart circle[role="button"]').dispatchEvent(new MouseEvent('click',{bubbles:true}))`)
  assert.ok(await evaluate(`document.querySelector('.ow-chart-tooltip').textContent.includes(': 9')`))
  for (const width of [320, 360, 768, 1024, 1440]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 640 }); await wait(80)
    assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true, `Overflow ${width}`)
  }
  await select('Reporting gym', '2')
  await until(`document.body.innerText.includes('Analytics Gym 2') && document.querySelectorAll('.ow-chart svg').length===2`)
  await wait(200)
  for (const suffix of ['', '/bookings', '/transactions', '/attendance']) assert.ok(calls.some(path => path.includes(`/analytics${suffix}?`) && path.includes('gym_id=2')))
  await select('Booking outcome', 'attended'); await wait(200)
  assert.ok(calls.some(path => path.includes('/bookings?') && path.includes('category=attended')))
  await button('Next'); await wait(200)
  assert.ok(calls.some(path => path.includes('/bookings?') && path.includes('offset=10')))
  await select('Payment status', 'REFUNDED'); await wait(200)
  assert.ok(calls.some(path => path.includes('payment_status=REFUNDED')))
  fail = true; await button('Refresh reports'); await until(`document.body.innerText.includes('Something went wrong')`)
  fail = false; await evaluate(`Array.from(document.querySelectorAll('main button')).find(el=>/try again/i.test(el.textContent)).click()`); await until(`document.querySelectorAll('.ow-chart svg').length===2`)
  await evaluate(`Array.from(document.querySelectorAll('.fg-date-presets button')).find(el=>el.textContent==='Custom').click()`)
  for (const label of ['Start date', 'End date']) await evaluate(`(() => {const el=document.querySelector('input[aria-label="${label}"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'2026-10-01');el.dispatchEvent(new Event('input',{bubbles:true}))})()`)
  await button('Apply range'); await until(`document.body.innerText.includes('No completed visits in this period') && document.body.innerText.includes('No recognized revenue in this period')`)
  assert.deepEqual(errors, [])
  console.log('PASS analytics charts/tooltips, All Gyms and selected scope, filters/pagination, refresh/error/empty states, responsive 320-1440px')
} finally { ws.close(); await target.dispose() }