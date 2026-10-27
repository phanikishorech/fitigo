// Isolated customer review/history fixture; no production review submissions.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, hasMembership = true, saved = null, submissions = 0, fail = false
const pending = new Map(), errors = []
const user = { id: 1, first_name: 'Review', last_name: 'Customer', email: 'review@example.com' }
const visit = { booking_id: 7, booking_status: 'COMPLETED', attendance_status: 'ATTENDED', can_review: true, gym_id: 42, gym_name: 'Feedback Gym', gym_location: 'Test City', access_type: 'Gym Workout', class_name: null, visit_date: '2026-10-27', start_time: '10:00:00', end_time: '11:00:00', membership_covered: false, amount_paid: '150', currency: 'INR', booking_created_at: '2026-10-27T00:00:00Z' }
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 15000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw Error(result.exceptionDetails.text); return result.result.value }
async function until(expression) { for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await wait(80) } throw Error(`${expression}: ${await evaluate('document.body.innerText')}`) }
async function go(path, text) { await command('Page.navigate', { url: origin + path }); await until(`document.body.innerText.includes(${JSON.stringify(text)})`) }
async function click(text) { await evaluate(`Array.from(document.querySelectorAll('main button')).find(el=>el.textContent.trim()===${JSON.stringify(text)}).click()`) }
function fixture(path, method, body, query) {
  if (path.endsWith('/auth/session')) return { user, roles: ['CUSTOMER'] }
  if (path.endsWith('/users/me')) return user
  if (path === '/api/v1/profile') return { user_id: 1, full_name: 'Review Customer', membership_status: hasMembership ? 'ACTIVE' : null, has_membership_history: hasMembership, profile_image: null }
  if (path.endsWith('/profile/bookings')) { assert.equal(query.get('source'), 'individual'); return [{ ...visit, review_id: saved?.id, review_rating: saved?.rating, review_status: saved?.status }] }
  if (path.endsWith('/profile/membership-visits')) return { total: 1, items: [{ id: 2, gym_id: 42, gym_name: 'Membership Gym', membership_id: 3, checkin_time: '2026-10-27T09:00:00+05:30' }] }
  if (/\/profile\/bookings\/\d+\/review$/.test(path)) return { booking_id: path.includes('/8/') ? 8 : 7, gym_id: 42, gym_name: 'Feedback Gym', can_review: !path.includes('/8/'), reason: 'A paid individual booking and successful check-in are required.', review: saved }
  if (path === '/api/v1/gyms/42/reviews' && method === 'POST') {
    assert.equal(body.booking_id, 7); assert.equal(body.rating, 4); assert.equal(body.comment, 'Great equipment')
    if (!fail) { submissions++; saved = { id: 1, rating: body.rating, comment: body.comment, status: 'PUBLISHED' } }
    return saved || {}
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
    try { const data = fixture(url.pathname, request.method, request.postData ? JSON.parse(request.postData) : {}, url.searchParams); await command('Fetch.fulfillRequest', { requestId, responseCode: fail && request.method === 'POST' ? 503 : 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(data)).toString('base64') }) }
    catch (error) { errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
  }
}
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: "localStorage.setItem('fitigo:access_token','isolated-review-fixture')" })
  await go('/profile', 'Membership visit history')
  assert.equal(await evaluate(`document.querySelector('main').innerText.includes('Check-in history')`), false)
  assert.ok(await evaluate(`document.querySelector('main').innerText.includes('My bookings')`))
  hasMembership = false; await go('/profile', 'My bookings')
  assert.equal(await evaluate(`document.querySelector('main').innerText.includes('Membership visit history')`), false)
  await go('/profile/visits', 'Membership Gym')
  assert.equal(await evaluate(`document.querySelector('main').innerText.includes('Feedback Gym')`), false)
  await go('/bookings', 'Rate visit')
  assert.ok(await evaluate(`document.querySelector('main').innerText.includes('My bookings')`))
  await evaluate(`document.querySelector('main a[href="/reviews/7"]').click()`)
  await until(`document.body.innerText.includes('How was your gym visit?')`)
  assert.ok(await evaluate(`document.querySelector('button[type="submit"]').disabled`))
  await evaluate(`document.querySelector('button[aria-label="4 stars"]').click()`)
  await evaluate(`(() => {const el=document.querySelector('textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(el,'Great equipment');el.dispatchEvent(new Event('input',{bubbles:true}))})()`)
  for (const width of [360, 768, 1440]) { await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 640 }); await wait(80); assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'), true) }
  fail = true; await click('Submit review'); await until(`!!document.querySelector('[role="alert"]')`); assert.equal(submissions, 0)
  fail = false; await click('Submit review'); await until(`document.body.innerText.includes('Thanks for your feedback!')`); assert.equal(submissions, 1)
  await go('/reviews/7', 'Update your gym feedback')
  assert.equal(await evaluate(`document.querySelector('textarea').value`), 'Great equipment')
  assert.equal(await evaluate(`document.querySelector('button[aria-label="4 stars"]').getAttribute('aria-pressed')`), 'true')
  await click('Save review'); await until(`document.body.innerText.includes('Thanks for your feedback!')`); assert.equal(submissions, 2)
  await go('/profile/reviews', 'Edit review'); assert.ok(await evaluate(`document.body.innerText.includes('Your rating: 4/5')`))
  await go('/reviews/8', 'This visit is not eligible for feedback')
  assert.equal(await evaluate(`!!document.querySelector('main textarea')`), false)
  assert.deepEqual(errors, [])
  console.log('PASS profile links, membership-only history, individual bookings, review eligibility/rating/comment/create/edit/error retry and responsive layout')
} finally { ws.close(); await target.dispose() }