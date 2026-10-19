// Isolated browser API fixtures. No live bookings, payments or credentials.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const target = await isolatedBrowserTarget()
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, status = 'READY', qrCalls = 0, shortExpiry = false, group = false, firstUsed = false, verifiedCheckin = true
const pending = new Map(), errors = []
const date = new Date().toISOString().slice(0, 10)
const user = { id: 1, first_name: 'John', last_name: 'Purchaser', email: 'booking@example.test' }
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const response = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (response.exceptionDetails) throw Error(response.exceptionDetails.exception?.description); return response.result.value }
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until(expression) { for (let i = 0; i < 150; i++) { if (await evaluate(expression)) return; await wait(100) } throw Error(`Not ready: ${expression}; ${await evaluate('document.body.innerText')}`) }
async function click(text) { await evaluate(`Array.from(document.querySelectorAll('button')).find(button => button.textContent.trim() === ${JSON.stringify(text)}).click()`) }
const access = () => ({ access_type: 'BOOKING_ACCESS', status, message: status === 'READY' ? 'Ready' : status === 'BOOKING_ALREADY_USED' ? 'This booking has already been used.' : 'Booking cancelled.', qr_available: status === 'READY', can_set_visitors: false, passes: (group ? [99, 100] : [99]).map(id => {
  const used = status === 'BOOKING_ALREADY_USED' || (id === 99 && firstUsed)
  return { qr_id: id, status: used ? 'USED' : 'ACTIVE', visitor_name: id === 99 ? 'David Visitor' : 'Mary Visitor', checked_in_at: used && verifiedCheckin ? '2026-10-09T18:00:00+05:30' : null }
}) })
function fixture(path, request) {
  if (path.endsWith('/auth/session')) return { user, roles: ['CUSTOMER'] }
  if (path.endsWith('/users/me')) return user
  if (path.endsWith('/bookings/42/qr')) {
    assert.equal(request.method, 'POST'); qrCalls++
    return { booking_id: 42, access_type: 'BOOKING_ACCESS', passes: (group ? [99, 100] : [99]).map(id => ({ qr_id: id, visitor_name: id === 99 ? 'David Visitor' : 'Mary Visitor', status: 'ACTIVE', qr_token: `GYMACCESS:opaque-booking-fixture-${id}`, valid_from: new Date(Date.now() - 60000).toISOString(), expires_at: new Date(Date.now() + (shortExpiry ? 1200 : 600000)).toISOString() })) }
  }
  if (path.endsWith('/bookings/42')) return { id: 42, gym_id: 19, slot_date: date, quantity: 1, total_price: '100', currency: 'INR', status: 'CONFIRMED', visitor_names: ['David Visitor'], access: access(), payment: { status: 'PAID', amount: '100', currency: 'INR', provider: 'WALLET' } }
  if (path.endsWith('/profile/bookings')) return [{ booking_id: 42, gym_id: 19, gym_name: 'Booking Fixture Gym', booking_status: 'CONFIRMED', attendance_status: null, access_type: 'Gym access', visit_date: date, start_time: '10:00:00', end_time: '14:00:00', membership_covered: false, amount_paid: '100', currency: 'INR', booking_access: access() }]
  if (path.endsWith('/gyms/19/details')) return { gym_id: 19, gym_name: 'Booking Fixture Gym', location: { full_address: '19 Fixture Street' }, rules: [] }
  throw Error(`Unexpected API ${path}`)
}
ws.onmessage = async event => {
  const message = JSON.parse(event.data), item = pending.get(message.id)
  if (item) { clearTimeout(item.timer); pending.delete(message.id); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result) }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
  if (message.method === 'Fetch.requestPaused') {
    const { requestId, request } = message.params
    try { await command('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(fixture(new URL(request.url).pathname, request))).toString('base64') }) }
    catch (error) { errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }).catch(() => {}) }
  }
}
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fitigo:access_token','isolated-booking-fixture')` })
  await command('Page.navigate', { url: 'http://localhost:5173/bookings' })
  await until(`document.body.innerText.includes('Show Booking QR')`)
  assert.equal(qrCalls, 0)
  await evaluate(`Array.from(document.querySelectorAll('a')).find(a => a.textContent === 'Show Booking QR').click()`)
  await until(`document.querySelector('button') && document.body.innerText.includes('Booking details')`)
  await click('Show Booking QR')
  await until(`!!document.querySelector('svg[aria-label="Booking QR for David Visitor"]')`)
  assert.equal(qrCalls, 1)
  assert.equal(await evaluate(`location.pathname`), '/bookings/42')
  for (const width of [320, 360, 390, 768, 916, 1440]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: width === 916 ? 814 : 1000, deviceScaleFactor: 1, mobile: width < 768 })
    assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), true)
    const layout = await evaluate(`(() => {
      const svg = document.querySelector('svg[aria-label="Booking QR for David Visitor"]')
      const card = svg.closest('section')
      const qr = svg.getBoundingClientRect(), panel = card.getBoundingClientRect()
      return { offset: Math.abs((qr.left + qr.width / 2) - (panel.left + panel.width / 2)), width: qr.width, height: qr.height, fits: qr.left >= panel.left && qr.right <= panel.right }
    })()`)
    assert.ok(layout.offset <= 1, `QR must be centered at ${width}px; offset ${layout.offset}px`)
    assert.ok(layout.width > 0 && Math.abs(layout.width - layout.height) <= 1, 'QR remains visible and square')
    assert.equal(layout.fits, true, `QR fits inside its card at ${width}px`)
  }
  status = 'BOOKING_ALREADY_USED'
  await until(`document.querySelector('dialog').innerText.includes('Your access is approved')`)
  assert.equal(await evaluate(`!!document.querySelector('svg[aria-label="Booking QR for David Visitor"]')`), false)
  assert.equal(await evaluate(`!!document.querySelector('dialog [role="alert"]')`), false)
  assert.equal(await evaluate(`document.querySelector('dialog').innerText.includes('Refresh booking access')`), false)
  assert.equal(await evaluate(`document.querySelector('dialog').innerText.includes('Checked in') && document.querySelector('dialog').innerText.includes('IST')`), true)
  assert.equal(qrCalls, 1, 'Polling never generates more tokens')
  for (const width of [320, 390, 916, 1440]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 768 })
    assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), true)
  }
  await evaluate(`document.querySelector('button[aria-label="Close dialog"]').click()`)
  await until(`!document.querySelector('dialog') && document.body.innerText.includes('Your access is approved')`)
  // A separate visit reload verifies partial group use, then full group approval.
  status = 'READY'; group = true
  await command('Page.navigate', { url: 'http://localhost:5173/bookings/42' })
  await until(`Array.from(document.querySelectorAll('button')).some(b => b.textContent === 'Show Booking QR')`)
  await click('Show Booking QR')
  await until(`!!document.querySelector('svg[aria-label="Booking QR for Mary Visitor"]')`)
  firstUsed = true
  await until(`document.querySelector('dialog').innerText.includes('Your access is approved')`)
  assert.equal(await evaluate(`!!document.querySelector('svg[aria-label="Booking QR for David Visitor"]')`), false)
  assert.equal(await evaluate(`!!document.querySelector('svg[aria-label="Booking QR for Mary Visitor"]')`), true)
  status = 'BOOKING_ALREADY_USED'
  await until(`document.querySelectorAll('dialog .fg-success[role="status"]').length === 2`)
  assert.equal(await evaluate(`document.querySelectorAll('dialog svg[role="img"]').length`), 0)
  status = 'READY'; group = false; firstUsed = false
  await command('Page.navigate', { url: 'http://localhost:5173/bookings/42' })
  await until(`Array.from(document.querySelectorAll('button')).some(b => b.textContent === 'Show Booking QR')`)
  await click('Show Booking QR')
  await until(`!!document.querySelector('svg[aria-label="Booking QR for David Visitor"]')`)
  // A used status without a recorded QR check-in must not imply approval.
  status = 'BOOKING_ALREADY_USED'; verifiedCheckin = false
  await until(`document.querySelector('dialog [role="alert"]')?.innerText.includes('already been used')`)
  assert.equal(await evaluate(`document.querySelector('dialog').innerText.includes('Your access is approved')`), false)
  status = 'READY'; verifiedCheckin = true; await click('Refresh booking access')
  await until(`!!document.querySelector('svg[aria-label="Booking QR for David Visitor"]')`)
  status = 'BOOKING_CANCELLED'
  await until(`document.body.innerText.includes('Booking cancelled.')`)
  assert.equal(await evaluate(`!!document.querySelector('svg[aria-label="Booking QR for David Visitor"]')`), false)
  status = 'READY'; shortExpiry = true; await click('Refresh booking access')
  await until(`!!document.querySelector('svg[aria-label="Booking QR for David Visitor"]')`)
  await until(`document.body.innerText.includes('QR unavailable or expired')`)
  assert.deepEqual(errors, [])
  console.log('PASS centered booking QR; verified individual/group scans show approval; remaining guest QR stays active; cancellation/expiry/unverified use never approve')
} finally { await command('Fetch.disable').catch(() => {}); ws.close(); await target.dispose() }