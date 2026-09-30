// TEST ONLY. Browser network fixtures; never imported by the application or production build.
// This verifies rendering and navigation, NOT connectivity or authorization of the live backend.
// Run separately from admin-browser-smoke.mjs, which uses real backend responses by default.
import assert from 'node:assert/strict'
const targets = await (await fetch('http://localhost:9231/json')).json()
const ws = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0; const pending = new Map()
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })) }) }
const date = '2026-09-30'; const created = `${date}T10:00:00`
const user = { id: 1, first_name: 'Test', last_name: 'Administrator', email: 'admin-fixture@example.test', phone: null, status: 'ACTIVE', created_at: created, roles: ['ADMIN'] }
const gyms = [
  { id: 3, owner_user_id: 2, name: 'Test Pending Gym', city: 'Test City', status: 'PENDING_APPROVAL', is_active: true, is_featured: false, created_at: created },
  { id: 2, owner_user_id: 2, name: 'Test Rejected Gym', city: 'Test City', status: 'REJECTED', is_active: true, is_featured: false, created_at: created },
  { id: 1, owner_user_id: 2, name: 'Test Approved Gym', city: 'Test City', status: 'APPROVED', is_active: true, is_featured: false, created_at: created }
]
const booking = { id: 1, status: 'CONFIRMED', slot_date: date, quantity: 2, total_price: '600.00', currency: 'INR', customer: { id: 3, first_name: 'Test', last_name: 'Customer', email: 'customer-fixture@example.test', phone: null }, gym: gyms[2], slot: { id: 1, name: 'Gym access', start_time: '07:00:00', end_time: '08:00:00' }, payment: { id: 1, provider: 'TEST', status: 'PAID', amount: '600.00', currency: 'INR', external_ref: null } }
let simulatedError = null; let identityRoles = ['ADMIN']; let cancelRequests = 0
function fixture(url, method) {
  const { pathname: path, searchParams: query } = new URL(url)
  if (path === '/api/v1/auth/login') return { access_token: 'test-only-admin-token', refresh_token: 'test-only-refresh' }
  if (path === '/api/v1/auth/logout') return { status: 'ok' }
  if (path === '/api/v1/users/me') return user
  if (path === '/api/v1/users/me/roles') return identityRoles
  if (path === '/api/v1/admin/ping') return { status: 'ok', user_id: 1 }
  if (path === '/api/v1/admin/dashboard/summary') return { users: { total: 3, customers: 1, gym_owners: 1 }, gyms: { total: 3, pending_approval: 1 }, bookings: { today: 1, upcoming: 1 }, revenue: { last_30d: '600.00', currency: 'INR' } }
  if (path === '/api/v1/admin/users') return query.has('q') ? [] : [user]
  if (/\/api\/v1\/admin\/users\/\d+$/.test(path)) return user
  if (path === '/api/v1/admin/users/1/status' && method === 'POST') { user.status = 'INACTIVE'; return { status: 'ok', user_id: 1, new_status: user.status } }
  if (path === '/api/v1/admin/gyms/3/approve' && method === 'POST') { gyms[0].status = 'APPROVED'; return { status: 'ok', gym_id: 3, new_status: gyms[0].status } }
  if (path === '/api/v1/admin/gyms/3/reject' && method === 'POST') { gyms[0].status = 'REJECTED'; return { status: 'ok', gym_id: 3, new_status: gyms[0].status } }
  if (path === '/api/v1/admin/bookings/1/cancel' && method === 'POST') { cancelRequests++; booking.status = 'CANCELLED'; booking.payment.status = 'REFUNDED'; return { status: 'ok', booking_id: 1, new_status: booking.status } }
  if (path === '/api/v1/admin/gyms') return query.has('status') ? gyms.filter(gym => gym.status === query.get('status')) : gyms
  if (path === '/api/v1/admin/bookings') return [booking]
  if (path === '/api/v1/admin/bookings/1') return booking
  if (path === '/api/v1/admin/reports/bookings/daily') return [{ day: date, total_bookings: 1, confirmed_bookings: 1, cancelled_bookings: 0, expired_bookings: 0, paid_amount_total: '600.00' }]
  if (path === '/api/v1/notifications/me') return []
  if (/\/api\/v1\/gyms\/\d+$/.test(path)) return { ...gyms.find(gym => gym.id === Number(path.split('/').pop())), description: 'Test-only customer-facing preview.', phone: null, email: null, address_line_1: 'Test Street', address_line_2: null, state: null, country: null, postal_code: null, latitude: null, longitude: null, gym_price_per_person: '300.00', has_classes: false, updated_at: created, images: [], facilities: [{ id: 1, name: 'Cardio', description: null, icon: null }], operating_hours: [{ day_of_week: 0, open_time: '06:00:00', close_time: '22:00:00', is_closed: false }] }
  throw new Error(`Unexpected fixture request: ${method} ${path}`)
}
const failures = []
ws.onmessage = async event => {
  const message = JSON.parse(event.data)
  if (message.id && pending.has(message.id)) { const item = pending.get(message.id); pending.delete(message.id); message.error ? item.reject(new Error(message.error.message)) : item.resolve(message.result) }
  if (message.method === 'Fetch.requestPaused') {
    const { requestId, request } = message.params
    if (simulatedError && request.url.includes(simulatedError.path)) {
      if (simulatedError.status === 0) await command('Fetch.failRequest', { requestId, errorReason: 'ConnectionFailed' })
      else await command('Fetch.fulfillRequest', { requestId, responseCode: simulatedError.status, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify({ detail: 'SQL traceback private diagnostics' })).toString('base64') })
      return
    }
    try { const result = fixture(request.url, request.method); await command('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(result)).toString('base64') }) }
    catch (error) { failures.push(error.message); await command('Fetch.fulfillRequest', { requestId, responseCode: 500, body: Buffer.from('{}').toString('base64') }) }
  }
}
try {
  await command('Fetch.enable', { patterns: [{ urlPattern: '*://localhost:5173/api/v1/*' }] })
  process.env.FITIGO_TEST_EMAIL = user.email; process.env.FITIGO_TEST_PASSWORD = 'test-only-fixture-password'; process.env.FITIGO_FIXTURE_MODE = '1'
  console.log('TEST FIXTURE MODE: subsequent authenticated checks validate UI only, not live API behavior.')
  await import('./admin-browser-smoke.mjs')
  const evaluate = async expression => { const result = await command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (result.exceptionDetails) throw new Error(result.exceptionDetails.text); return result.result.value }
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
  async function until(expression) { for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await wait(80) } throw new Error(`Fixture check timed out: ${expression}; ${await evaluate('document.body.innerText.slice(-1000)')}`) }
  async function visit(path, text) { await command('Page.navigate', { url: `http://localhost:5173${path}` }); await until(`document.body.innerText.includes(${JSON.stringify(text)})`); await until(`!document.querySelector('[aria-label="Loading"]')`) }
  async function click(text, selector = 'button') { await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(el=>el.textContent.trim()===${JSON.stringify(text)}).click()`); await wait(80) }
  await evaluate(`localStorage.setItem('fitigo:access_token','test-only-admin-token')`)
  await visit('/admin/gyms/3/review', 'Gym information')
  await click('Approve Gym'); await click('Approve Gym','dialog button'); await until(`!document.querySelector('dialog[open]')`); await until(`document.querySelector('main')?.innerText.includes('This approved gym is enabled')`)
  await visit('/admin/gyms/3', 'Gym information'); await click('Reject Gym'); await until(`!!document.querySelector('dialog[open]')`)
  await evaluate(`(() => {const el=document.querySelector('textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(el,'Missing information');el.dispatchEvent(new Event('input',{bubbles:true}));})()`)
  await click('Reject Gym','dialog button'); await until(`!document.querySelector('dialog[open]')`); await until(`document.querySelector('main')?.innerText.includes('This gym is rejected')`)
  await visit('/admin/users/1', 'Account information'); await click('Deactivate user'); await click('Deactivate user','dialog button'); await until(`!document.querySelector('dialog[open]')`); await until(`document.querySelector('main')?.innerText.includes('Inactive')`)
  await visit('/admin/bookings/1', 'Booking information'); await click('Force Cancel Booking'); await until(`document.querySelector('dialog')?.innerText.includes('Payment received.')`)
  // Two rapid submissions still produce one POST because useMutation has a synchronous lock.
  await evaluate(`document.querySelector('dialog form').requestSubmit();document.querySelector('dialog form').requestSubmit()`)
  await until(`!document.querySelector('dialog[open]')`); await until(`document.querySelector('main')?.innerText.includes('Refunded')`); assert.equal(cancelRequests, 1)
  simulatedError = { path: '/admin/bookings/1/cancel', status: 409 }
  await click('Force Cancel Booking'); await click('Force Cancel','dialog button'); await until(`document.querySelector('dialog')?.innerText.includes('record may have changed')`)
  assert.equal(await evaluate(`document.body.innerText.includes('SQL traceback')`), false); await click('Keep unchanged','dialog button'); simulatedError = null
  console.log('PASS TEST FIXTURES: approve/reject/user mutation refresh, paid cancellation state, duplicate submission prevention and conflict error')
  for (const status of [500, 0, 403]) {
    simulatedError = { path: '/admin/users?', status }; await visit('/admin/users', status === 0 ? 'Unable to connect' : status === 403 ? 'Access denied.' : 'Unable to load this view')
    assert.equal(await evaluate(`document.body.innerText.includes('SQL traceback')`), false); simulatedError = null
    await click('Try again'); await until(`!!document.querySelector('main a[href="/admin/users/1"]')`)
  }
  simulatedError = { path: '/admin/users?', status: 401 }; await visit('/admin/users','Your session has expired.'); simulatedError = null
  identityRoles = ['CUSTOMER']; await evaluate(`localStorage.setItem('fitigo:access_token','test-only-non-admin')`); await visit('/admin/dashboard', 'Access denied'); assert.equal(await evaluate('location.pathname'), '/admin/access-denied')
  await evaluate(`localStorage.removeItem('fitigo:access_token');localStorage.removeItem('fitigo:refresh_token')`)
  console.log('PASS TEST FIXTURES: sanitized server/network/403 errors, retry, 401 expiration and non-admin rejection')
  if (failures.length) throw new Error(failures.join('\n'))
} finally { await command('Fetch.disable'); ws.close(); delete process.env.FITIGO_TEST_EMAIL; delete process.env.FITIGO_TEST_PASSWORD; delete process.env.FITIGO_FIXTURE_MODE }