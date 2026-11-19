// Isolated browser + intercepted APIs only; no real accounts or cart writes.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://127.0.0.1:5173'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let seq = 0, read = false, failSave = false, saves = [], adds = 0, privateReads = 0
const pending = new Map(), errors = []
const user = { id: 1, first_name: 'Fixture', last_name: 'Customer', email: 'fixture@example.test', status: 'ACTIVE' }
const original = { id: 8, gym_id: 19, gym_name: 'Fixture gym', booking_type: 'GYM', booking_date: '2027-01-03', preferred_start_time: '14:15:00', preferred_end_time: '15:15:00', member_count: 2, visitor_names: ['Alice Fixture', 'Bob Fixture'], price_per_person: '100.00', total_price: '200.00', currency: 'INR', status: 'ACTIVE', can_edit: true, updated_at: '2026-11-12T12:00:00' }
let items = [{ ...original }]
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++seq, timer = setTimeout(() => reject(Error(method)), 15000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const response = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (response.exceptionDetails) throw Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text); return response.result.value }
async function until(expression) { for (let i = 0; i < 180; i++) { if (await evaluate(`Boolean(${expression})`)) return; await new Promise(resolve => setTimeout(resolve, 70)) } throw Error(JSON.stringify({ expression, body: await evaluate('document.body.innerText'), errors })) }
async function click(text, selector = 'button') { const expression = `Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(el=>el.textContent.trim()===${JSON.stringify(text)})`; await until(`!!(${expression})`); await evaluate(`${expression}.click()`) }
async function field(selector, value, type = 'HTMLInputElement') { await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(${type}.prototype,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('${type === 'HTMLSelectElement' ? 'change' : 'input'}',{bubbles:true}))})()`) }
async function page(path, text) { await command('Page.navigate', { url: origin + path }); await until(`document.body.innerText.includes(${JSON.stringify(text)})`) }
ws.onmessage = async event => {
  const message = JSON.parse(event.data), p = pending.get(message.id)
  if (p) { clearTimeout(p.timer); pending.delete(message.id); message.error ? p.reject(Error(message.error.message)) : p.resolve(message.result) }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text)
  if (message.method !== 'Fetch.requestPaused') return
  const { request, requestId } = message.params, url = new URL(request.url), path = url.pathname
  let body = {}, status = 200
  if (/\/cart\/|\/notifications\//.test(path)) privateReads++
  if (path.endsWith('/auth/session')) body = { user, roles: ['CUSTOMER'] }
  else if (path.endsWith('/users/me')) body = user
  else if (path.endsWith('/profile/membership')) body = { status: 'NO_ACTIVE_MEMBERSHIP', membership_id: null }
  else if (path.endsWith('/memberships/me')) body = []
  else if (path.endsWith('/gyms/discover')) body = { gyms: [], total_count: 0, page: 1, page_size: 8, has_more: false }
  else if (path.endsWith('/meta/gym-types') || path.endsWith('/facilities')) body = []
  else if (path.endsWith('/cart/summary')) body = { count: items.filter(item => item.status === 'ACTIVE').length }
  else if (path.endsWith('/cart/items')) body = items
  else if (path.endsWith('/cart/items/8')) {
    if (request.method === 'PUT') {
      const payload = JSON.parse(request.postData); saves.push(payload)
      if (failSave) { status = 409; body = { detail: 'Fixture conflict: reload draft before saving.' } }
      else { items[0] = { ...items[0], ...payload, preferred_end_time: '17:30:00', updated_at: '2026-11-12T12:00:01' }; body = items[0] }
    } else if (request.method === 'DELETE') { items = []; body = { status: 'ok' } }
    else body = items[0]
  }
  else if (path.endsWith('/cart/items/gym')) { adds++; const payload = JSON.parse(request.postData); body = { ...original, ...payload }; items = [body] }
  else if (path.endsWith('/notifications/inbox/1/read')) { read = true; body = { status: 'ok' } }
  else if (path.endsWith('/notifications/inbox')) body = { enabled: true, total: 1, unread_count: read ? 0 : 1, items: [{ id: 1, title: 'Fixture booking update', body: 'Your visit was updated.', category: 'OPERATIONAL', created_at: '2026-11-12T12:00:00Z', read_at: read ? '2026-11-12T12:01:00Z' : null, email_status: 'NOT_REQUESTED', error_code: null }] }
  else if (path.endsWith('/notifications/preferences')) body = { enabled: true, operational_email: false, email_available: false, message: 'Fixture email preferences' }
  else if (path.endsWith('/gyms/19/booking-options')) body = { gym_id: 19, gym_name: 'Fixture gym', gym_price_per_person: '100', has_classes: false, server_now: '2027-01-01T12:00:00+05:30', membership_status: {}, available_access_types: [], workout_areas: [] }
  else if (path.endsWith('/gyms/19/operating-hours')) body = { gym_id: 19, date: url.searchParams.get('date'), day_of_week: 0, open_time: '06:00:00', close_time: '23:00:00', is_closed: false }
  else if (path.endsWith('/auth/otp/options')) body = { email_available: false, mobile_available: false }
  else if (path.endsWith('/meta/support')) body = { email: null, ticketing_available: false }
  else { errors.push('Unexpected API: ' + path); status = 404 }
  await command('Fetch.fulfillRequest', { requestId, responseCode: status, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') })
}
try {
  await command('Page.enable'); await command('Runtime.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  const script = await command('Page.addScriptToEvaluateOnNewDocument', { source: "localStorage.setItem('fitigo:access_token','customer-activity-fixture');Object.defineProperty(navigator,'geolocation',{value:undefined,configurable:true});" })
  await page('/home', 'Map View')
  await until("document.querySelector('a[aria-label=\"Notifications, 1 unread\"]') && document.querySelector('a[aria-label=\"Your cart, 1 visit draft\"]')")
  for (const width of [360, 768, 1024, 1280, 1440]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 640 })
    assert.equal(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'), true, `header width ${width}`)
  }
  await evaluate("document.querySelector('a[aria-label=\"Notifications, 1 unread\"]').click()")
  await until("document.body.innerText.includes('Fixture booking update')")
  await click('Mark read'); await until("document.body.innerText.includes('0 unread') && !!document.querySelector('header a[aria-label=\"Notifications\"]')")
  await page('/settings', 'Notification preferences')
  assert.equal(await evaluate("document.body.innerText.includes('Unread only')"), false)
  await page('/cart', 'Edit Visit'); await click('Edit Visit', 'a')
  await until("document.body.innerText.includes('Save visit changes')")
  assert.equal(await evaluate("document.querySelector('input[type=date]').value"), '2027-01-03')
  assert.equal(await evaluate("document.querySelector('select[aria-label=\"Start hour (IST)\"]').value"), '14')
  assert.equal(await evaluate("document.querySelector('select[aria-label=\"Start minutes\"]').value"), '15')
  assert.deepEqual(await evaluate("Array.from(document.querySelectorAll('fieldset input')).map(el=>el.value)"), ['Alice Fixture', 'Bob Fixture'])
  await field('input[type=date]', '2027-01-04')
  await until("!!document.querySelector('select[aria-label=\"Start hour (IST)\"]')")
  await field('select[aria-label="Start hour (IST)"]', '16', 'HTMLSelectElement')
  await field('select[aria-label="Start minutes"]', '30', 'HTMLSelectElement')
  await field('fieldset input', 'Alice Updated')
  failSave = true; await click('Save visit changes'); await until("document.body.innerText.includes('Fixture conflict')")
  assert.equal(items[0].visitor_names[0], 'Alice Fixture')
  assert.equal(await evaluate("document.querySelector('fieldset input').value"), 'Alice Updated')
  failSave = false; await click('Save visit changes'); await until("location.pathname==='/cart' && document.body.innerText.includes('Alice Updated')")
  assert.equal(adds, 0); assert.equal(items.length, 1); assert.equal(items[0].id, 8)
  assert.equal(saves.at(-1).preferred_start_time, '16:30'); assert.equal(saves.at(-1).booking_date, '2027-01-04')
  assert.equal(saves.at(-1).expected_updated_at, original.updated_at)
  await click('Edit Visit', 'a'); await until("document.body.innerText.includes('Save visit changes')")
  await field('fieldset input', 'Unsaved name'); await click('Cancel editing', 'a'); await until("location.pathname==='/cart'")
  assert.equal(items[0].visitor_names[0], 'Alice Updated')
  await click('Remove'); await until("document.body.innerText.includes('Your cart is empty') && !!document.querySelector('header a[aria-label=\"Your cart\"]')")
  await page('/gyms/19/book/schedule', 'Check availability & add to cart')
  await field('input[type=date]', '2027-01-04'); await until("!!document.querySelector('select[aria-label=\"Start hour (IST)\"]')")
  await field('select[aria-label="Start hour (IST)"]', '14', 'HTMLSelectElement'); await field('select[aria-label="Start minutes"]', '15', 'HTMLSelectElement'); await field('fieldset input', 'New visitor')
  await click('Check availability & add to cart'); await until("location.pathname==='/cart' && !!document.querySelector('header a[aria-label=\"Your cart, 1 visit draft\"]')")
  assert.equal(adds, 1)
  items[0].can_edit = false; items[0].status = 'PAYMENT_PENDING'
  await page('/cart/items/8/edit', 'This visit cannot be edited')
  await command('Page.removeScriptToEvaluateOnNewDocument', { identifier: script.identifier })
  await evaluate("localStorage.removeItem('fitigo:access_token')")
  const before = privateReads
  await page('/home', 'Map View'); await new Promise(resolve => setTimeout(resolve, 300))
  assert.equal(privateReads, before)
  assert.equal(await evaluate("document.querySelectorAll('header .fg-icon-count').length"), 0)
  assert.deepEqual(errors, [])
  console.log('PASS: Home bell/unread badge, mark read, settings preferences only, cart badge add/remove, prefilled edit/save/cancel/error, no duplicate purchase, checkout protection, anonymous privacy, 360–1440px header layouts.')
} finally { ws.close(); await target.dispose() }