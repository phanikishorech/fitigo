// Isolated browser fixtures only. All API calls intercepted; no live writes.
import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const target = await isolatedBrowserTarget()
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, scope = 'MULTI_GYM', status = 'ACTIVE', failure = null, delayQr = false, issuedStatus = null, shortExpiry = false
let qrRequests = 0, gymRequests = 0, calendarRequests = 0
const pending = new Map(), errors = []
const day = new Date().toISOString().slice(0, 10)
const user = { id: 1, first_name: 'Access', last_name: 'Member', email: 'access@example.test' }
const gym = { gym_id: 42, gym_name: 'Assigned Movement Studio', images: [], location: { full_address: '42 Fixture Street', city: 'Fixture City' }, membership_access: { status: 'INCLUDED' }, opening_hours: { weekly: [] } }
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value }
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until(expression) { for (let i = 0; i < 300; i++) { if (await evaluate(expression)) return; await wait(80) } throw Error(`Not ready: ${expression}; ${await evaluate('document.body.innerText')}`) }
async function visit(path, text) { await command('Page.navigate', { url: 'http://localhost:5173' + path }); await until(`document.body.innerText.includes(${JSON.stringify(text)})`); await until(`!document.querySelector('[aria-label="Loading"]')`) }
async function click(text, selector = 'button') { await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(e=>e.textContent.trim()===${JSON.stringify(text)}).click()`); await wait(100) }
async function width(w) { await command('Emulation.setDeviceMetricsOverride', { width: w, height: 1000, deviceScaleFactor: 1, mobile: w < 768 }); await wait(80); assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'), true, `Overflow at ${w}`) }
async function shot(name) { const image = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }); await writeFile(join(tmpdir(), name), Buffer.from(image.data, 'base64')) }
async function personalOnly() { assert.equal(await evaluate(`/Book for Others|Add to Cart|Guest Booking|Friend|Family|Paid Visit Booking/i.test(document.querySelector('main').innerText)`), false) }
function fixture(path) {
  if (path === '/api/v1/auth/session') return { user, roles: ['CUSTOMER'] }
  if (path === '/api/v1/users/me') return user
  if (path === '/api/v1/customer/access-calendar') {
    calendarRequests++
    return { access_type: ['PAUSED', 'EXPIRED', 'NO_ACCESS'].includes(status) ? null : scope, gym: scope === 'SINGLE_GYM' && status === 'ACTIVE' ? { id: 42, name: gym.gym_name } : null, days: [{ date: day, status: 'TODAY', qr_available: status === 'ACTIVE', qr_status: status === 'EXPIRED' ? 'NO_ACCESS' : status, gym_name: status === 'USED' ? gym.gym_name : null, checkin_time: status === 'USED' ? '08:15:00' : null }] }
  }
  if (path === '/api/v1/profile/membership') return { membership_id: 1, status: status === 'USED' ? 'ACTIVE' : status === 'NO_ACCESS' ? 'CANCELLED' : status, membership_scope: scope, plan_name: 'Backend plan', start_date: day + 'T00:00:00Z', end_date: '2026-12-01T00:00:00Z', active_gyms: [], membership_features: [] }
  if (path === '/api/v1/memberships/me') return [{ id: 1, gym_id: scope === 'SINGLE_GYM' ? 42 : null, membership_type: scope }]
  if (path === '/api/v1/gyms/42/details') { gymRequests++; return gym }
  if (path === '/api/v1/memberships/me/1/pause') return { currently_paused: true, current_pause: { end_date: '2026-10-10', resumes_on: '2026-10-11' } }
  if (path === '/api/v1/customer/access/today') {
    qrRequests++
    const state = issuedStatus || status
    if (issuedStatus === 'PAUSED') status = 'PAUSED'
    if (state !== 'ACTIVE') return { status: state, gym_name: gym.gym_name, used_at: day + 'T08:15:00Z' }
    return { status: 'ACTIVE', access_type: scope, gym: scope === 'SINGLE_GYM' ? { id: 42, name: gym.gym_name } : null, qr_token: 'GYMACCESS:isolated-test-only-not-a-real-token', expires_at: new Date(Date.now() + (shortExpiry ? 1200 : 300000)).toISOString() }
  }
  if (path === '/api/v1/gyms/discover') return { gyms: [], total_count: 0, page: 1, page_size: 12, has_more: false }
  if (path === '/api/v1/meta/gym-types' || path === '/api/v1/facilities') return []
  throw Error(`Unexpected request: ${path}`)
}
ws.onmessage = async event => {
  const m = JSON.parse(event.data), p = pending.get(m.id)
  if (p) { clearTimeout(p.timer); pending.delete(m.id); m.error ? p.reject(Error(m.error.message)) : p.resolve(m.result) }
  if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.text)
  if (m.method === 'Fetch.requestPaused') {
    const { requestId, request } = m.params, path = new URL(request.url).pathname
    try {
      assert.equal(request.method, 'GET', 'My Access must not invoke booking/cart mutations')
      if (delayQr && path.endsWith('/access/today')) await wait(450)
      if (failure && path.includes(failure)) { await command('Fetch.failRequest', { requestId, errorReason: 'ConnectionFailed' }); return }
      await command('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(fixture(path))).toString('base64') })
    } catch (e) { errors.push(e.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }).catch(() => {}) }
  }
}
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fitigo:access_token','isolated-access-fixture');` })
  await visit('/my-access', 'Generate Visit QR'); assert.equal(qrRequests, 0); assert.equal(gymRequests, 0)
  assert.equal(await evaluate(`document.querySelector('main a[href="/gyms"]').textContent.trim()`), 'Find a Gym')
  for (const w of [360, 390, 768, 1024, 1440]) await width(w)
  await shot('fitigo-my-access-multi-desktop.png'); await width(390); await shot('fitigo-my-access-multi-mobile.png'); await personalOnly()
  await click('Find a Gym', 'a'); await until(`location.pathname==='/gyms'`)
  await visit('/my-access', 'Generate Visit QR'); delayQr = true
  await evaluate(`(()=>{const b=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('Generate Visit QR'));b.click();b.click()})()`)
  await until(`!!document.querySelector('[aria-label="Loading"]')`)
  await until(`!!document.querySelector('.fm-qr-frame svg')`); delayQr = false
  assert.equal(qrRequests, 1); assert.equal(gymRequests, 0)
  assert.equal(await evaluate(`location.pathname+location.search`), '/access/qr?generate=1')
  assert.equal(await evaluate(`document.querySelector('main').innerText.includes('Access Member') && document.querySelector('main').innerText.includes('Valid at eligible FitiGo gyms')`), true)
  await personalOnly(); await shot('fitigo-my-access-direct-qr.png')
  status = 'USED'; await until(`document.body.innerText.includes('Check-in Successful!')`)
  assert.equal(await evaluate(`!!document.querySelector('.fm-qr-frame')`), false); assert.equal(qrRequests, 1)
  await visit('/my-access', 'Your daily access has already been used today.'); await personalOnly()
  assert.equal(await evaluate(`document.querySelector('main').innerText.includes('Generate Visit QR')`), false)
  status = 'ACTIVE'; const beforeRefresh = calendarRequests
  await click('Refresh access status'); await until(`document.body.innerText.includes('Generate Visit QR')`)
  assert.ok(calendarRequests > beforeRefresh); assert.equal(await evaluate('location.pathname'), '/my-access'); assert.equal(qrRequests, 1)
  console.log('PASS Multi-Gym direct QR, double-click protection, read-only polling, USED and inline refresh')
  scope = 'SINGLE_GYM'; await visit('/my-access', 'Assigned Movement Studio')
  assert.equal(await evaluate(`!!document.querySelector('main a[href="/gyms"]')`), false)
  assert.equal(await evaluate(`document.querySelector('main').innerText.includes('42 Fixture Street')`), true)
  for (const w of [360, 390, 768, 1440]) await width(w)
  await shot('fitigo-my-access-single-desktop.png'); await width(390); await shot('fitigo-my-access-single-mobile.png')
  await click('Generate Visit QR'); await until(`!!document.querySelector('.fm-qr-frame svg')`)
  assert.equal(qrRequests, 2); assert.equal(await evaluate(`document.querySelector('.fm-qr-card').innerText.includes('Assigned Movement Studio')`), true)
  await personalOnly()
  for (const [state, text] of [['PAUSED', 'paused until: 10 Oct 2026'], ['EXPIRED', 'Membership Expired'], ['NO_ACCESS', 'Membership is not active.']]) {
    status = state; await visit('/my-access', text)
    assert.equal(await evaluate(`document.querySelector('main').innerText.includes('Generate Visit QR')`), false)
    assert.equal(await evaluate(`!!document.querySelector('main a[href="/gyms"]')`), false)
  }
  assert.equal(qrRequests, 2)
  console.log('PASS Single-Gym assigned gym and QR, paused dates, expired/inactive states')
  status = 'ACTIVE'; failure = '/customer/access-calendar'; await visit('/my-access', 'Unable to load access status.')
  assert.equal(await evaluate(`document.querySelector('main').innerText.includes('Membership is not active.')`), false)
  failure = null; await click('Retry'); await until(`document.body.innerText.includes('Generate Visit QR')`)
  failure = '/customer/access/today'; await click('Generate Visit QR'); await until(`document.body.innerText.includes('Unable to generate QR')`)
  assert.equal(await evaluate(`!!document.querySelector('.fm-qr-frame')`), false)
  failure = null; await click('Retry'); await until(`!!document.querySelector('.fm-qr-frame')`)
  await evaluate(`window.dispatchEvent(new Event('offline'))`); await until(`document.body.innerText.includes('Unable to connect')`)
  assert.equal(await evaluate(`!!document.querySelector('.fm-qr-frame')`), false)
  await click('Retry'); await until(`!!document.querySelector('.fm-qr-frame')`)
  shortExpiry = true; await visit('/access/qr?generate=1', 'Show this QR to gym staff'); await until(`document.body.innerText.includes('Refresh your access QR')`)
  assert.equal(await evaluate(`!!document.querySelector('.fm-qr-frame')`), false); shortExpiry = false
  issuedStatus = 'USED'; await visit('/access/qr?generate=1', 'Today’s Access Already Used')
  assert.equal(await evaluate(`!!document.querySelector('.fm-qr-frame')`), false); issuedStatus = null
  issuedStatus = 'PAUSED'; await visit('/access/qr?generate=1', 'paused until: 10 Oct 2026')
  assert.equal(await evaluate(`!!document.querySelector('.fm-qr-frame')`), false); issuedStatus = null
  status = 'ACTIVE'; issuedStatus = 'EXPIRED'; await visit('/access/qr?generate=1', 'Membership Expired')
  assert.equal(await evaluate(`!!document.querySelector('.fm-qr-frame')`), false); issuedStatus = null
  status = 'UNKNOWN'; await visit('/my-access', 'Unable to load access status.')
  assert.deepEqual(errors, [])
  console.log('PASS API/network and unknown-state errors, safe retries, offline hiding, server expiry and used/paused/expired issuance races')
} finally { await command('Fetch.disable').catch(() => {}); ws.close(); await target.dispose() }