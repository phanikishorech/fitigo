// Isolated fixtures: verify membership/home entry points without real QR writes.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, scope = 'MULTI_GYM', state = 'ACTIVE', fail = false, qrRequests = 0
const pending = new Map(), errors = [], calls = []
const day = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
const start = '2026-01-01T00:00:00Z', end = '2027-12-31T00:00:00Z'
const user = { id: 1, first_name: 'Entry', last_name: 'Member', email: 'entry@example.com' }
const gym = { gym_id: 42, gym_name: 'Assigned Movement Studio', images: [], location: { full_address: '42 Fixture Street', city: 'Fixture City' }, membership_access: { status: 'INCLUDED' }, opening_hours: { weekly: [] } }
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 15000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw Error(result.exceptionDetails.text); return result.result.value }
async function until(expression) { for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await wait(80) } throw Error(`${expression}: ${await evaluate('document.body.innerText')}`) }
async function visit(path, text) { await command('Page.navigate', { url: origin + path }); await until(`document.body.innerText.includes(${JSON.stringify(text)})`); await wait(150) }
async function widths() { for (const width of [360, 390, 768, 1440]) { await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 640 }); await wait(60); assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'), true, `Overflow ${width}`) } }
function fixture(path) {
  if (path.endsWith('/auth/session')) return { user, roles: ['CUSTOMER'] }
  if (path.endsWith('/users/me')) return user
  const status = state === 'USED' ? 'ACTIVE' : state
  if (path.endsWith('/profile/membership')) return { membership_id: state === 'NONE' ? null : 1, status, membership_scope: scope, plan_name: 'Fixture Plan', start_date: start, end_date: end, active_gyms: scope === 'SINGLE_GYM' ? [{ gym_id: 42, gym_name: gym.gym_name }] : [], membership_features: [] }
  if (path.endsWith('/memberships/me')) return state === 'NONE' ? [] : [{ id: 1, user_id: 1, gym_id: scope === 'SINGLE_GYM' ? 42 : null, plan_id: 1, membership_type: scope, status, start_at: start, end_at: end, payment_status: 'PAID', payment_provider: 'CASHFREE', terms_snapshot: { name: 'Fixture Plan', duration_value: 1, duration_unit: 'YEAR' } }]
  if (path.endsWith('/customer/access-calendar')) return { access_type: scope, gym: scope === 'SINGLE_GYM' ? { id: 42, name: gym.gym_name } : null, days: [{ date: day, status: 'TODAY', qr_status: state, qr_available: state === 'ACTIVE', gym_name: state === 'USED' ? gym.gym_name : null, checkin_time: state === 'USED' ? '10:00:00' : null }] }
  if (path.endsWith('/memberships/me/1/pause')) return { membership_id: 1, membership_status: status, pause_allowed: false, can_pause: false, max_pause_days: 0, pause_days_used: 0, pause_days_remaining: 0, currently_paused: state === 'PAUSED', current_pause: state === 'PAUSED' ? { end_date: day, resumes_on: '2027-01-01' } : null, history: [], original_end_at: end, current_end_at: end, reason_code: 'PAUSE_NOT_ALLOWED', timezone: 'Asia/Kolkata' }
  if (path.endsWith('/gyms/42/details')) return gym
  if (path.endsWith('/memberships/gyms/42/plans')) return [{ id: 1, name: 'Fixture Plan', duration_days: 365 }]
  if (path.endsWith('/customer/access/today')) { qrRequests++; return { status: 'ACTIVE', access_type: scope, gym: scope === 'SINGLE_GYM' ? { id: 42, name: gym.gym_name } : null, qr_token: 'GYMACCESS:fixture-membership-entry-not-valid', expires_at: new Date(Date.now() + 300000).toISOString() } }
  if (path.endsWith('/gyms/discover')) return { gyms: [], total_count: 0, page: 1, page_size: 8, has_more: false }
  if (path.endsWith('/meta/gym-types') || path.endsWith('/facilities')) return []
  throw Error(`Unexpected API ${path}`)
}
ws.onmessage = async event => {
  const message = JSON.parse(event.data), item = pending.get(message.id)
  if (item) { clearTimeout(item.timer); pending.delete(message.id); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result) }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
  if (message.method === 'Fetch.requestPaused') {
    const { requestId, request } = message.params, path = new URL(request.url).pathname; calls.push(path)
    try { assert.equal(request.method, 'GET'); const data = fixture(path); await command('Fetch.fulfillRequest', { requestId, responseCode: fail && path.endsWith('/customer/access-calendar') ? 503 : 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(data)).toString('base64') }) }
    catch (error) { errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
  }
}
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  const injected = await command('Page.addScriptToEvaluateOnNewDocument', { source: "localStorage.setItem('fitigo:access_token','member-entry-fixture')" })
  for (const type of ['MULTI_GYM', 'SINGLE_GYM']) {
    scope = type; state = 'ACTIVE'
    const before = qrRequests, mine = calls.filter(p => p.endsWith('/memberships/me')).length
    await visit('/membership', 'Generate Visit QR'); await widths()
    assert.equal(qrRequests, before)
    // React StrictMode replays initial read effects in development. The shared
    // access card must not add another membership-list request to those reads.
    assert.ok(calls.filter(p => p.endsWith('/memberships/me')).length - mine <= 2)
    await evaluate(`(() => {const button=Array.from(document.querySelectorAll('main button')).find(b=>b.textContent.includes('Generate Visit QR'));button.click();button.click()})()`)
    await until(`!!document.querySelector('.fm-qr-frame svg')`)
    assert.equal(await evaluate('location.pathname+location.search'), '/access/qr?generate=1')
    assert.equal(qrRequests, before + 1)
    await visit('/home', type === 'MULTI_GYM' ? 'You’re a FitiGo member' : 'You’re a member of Assigned Movement Studio'); await widths()
    assert.equal(qrRequests, before + 1)
    assert.equal(await evaluate(`document.querySelector('[aria-label="Your membership access"] a').getAttribute('href')`), '/my-access')
    await evaluate(`document.querySelector('[aria-label="Your membership access"] a').click()`)
    await until(`location.pathname==='/my-access' && document.body.innerText.includes('Generate Visit QR')`)
    assert.equal(qrRequests, before + 1)
  }
  const before = qrRequests
  for (const value of ['PAUSED', 'USED']) {
    state = value
    await visit('/membership', value === 'PAUSED' ? 'Membership Paused' : 'You’ve used your access today.')
    assert.equal(await evaluate(`document.querySelector('main').innerText.includes('Generate Visit QR')`), false)
    await visit('/home', value === 'PAUSED' ? 'Your membership is paused.' : 'You’ve already used today’s access.')
    assert.equal(await evaluate(`document.querySelector('[aria-label="Your membership access"]').innerText.includes('Book a visit today')`), false)
  }
  state = 'NONE'; await visit('/home', 'Your next workout.')
  await until(`!document.querySelector('[aria-label="Loading membership status"]')`)
  assert.equal(await evaluate(`!!document.querySelector('[aria-label="Your membership access"]')`), false)
  state = 'ACTIVE'; fail = true; await visit('/home', 'Unable to check your membership right now')
  fail = false; await evaluate(`Array.from(document.querySelectorAll('main button')).find(b=>b.textContent==='Retry membership status').click()`)
  await until(`!!document.querySelector('[aria-label="Your membership access"]')`)
  assert.equal(qrRequests, before)
  await command('Page.removeScriptToEvaluateOnNewDocument', { identifier: injected.identifier })
  await evaluate(`localStorage.clear();sessionStorage.clear()`)
  const reads = calls.filter(path => path.endsWith('/profile/membership')).length
  await visit('/home', 'Your next workout.')
  assert.equal(calls.filter(path => path.endsWith('/profile/membership')).length, reads)
  assert.equal(await evaluate(`!!document.querySelector('[aria-label="Your membership access"]')`), false)
  assert.deepEqual(errors, [])
  console.log('PASS membership/home Single-Gym and Multi-Gym entry, explicit QR generation once, My Access links, paused/used/nonmember/anonymous/error states, 360–1440px')
} finally { ws.close(); await target.dispose() }