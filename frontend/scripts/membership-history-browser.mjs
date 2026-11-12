// Intercept all API traffic: no working membership, QR or payment mutations.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://127.0.0.1:5199'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, mode = 'mixed'
const pending = new Map(), errors = [], pauseReads = []
const user = { id: 1, first_name: 'Membership', last_name: 'Fixture', email: 'fixture@example.com', phone: null }
function member(id, status, name) {
  return { id, user_id: 1, gym_id: null, plan_id: null, membership_type: 'MULTI_GYM', status,
    start_at: '2026-11-01T00:00:00Z', end_at: '2026-12-01T00:00:00Z', paid_amount: '1000.00', currency: 'INR',
    payment_provider: 'CASHFREE', payment_status: 'PAID', terms_snapshot: { name, duration_value: 1, duration_unit: 'MONTH' } }
}
const active = member(2, 'ACTIVE', 'Current monthly plan'), expired = member(1, 'EXPIRED', 'Previous expired plan'),
  cancelled = member(3, 'CANCELLED', 'Cancelled old plan'), paused = member(4, 'PAUSED', 'Paused current plan')
function records() {
  if (mode === 'only-current') return [active]
  if (mode === 'history-only') return [expired, cancelled]
  if (mode === 'empty') return []
  if (mode === 'paused') return [expired, paused]
  return [expired, active, cancelled] // Old row intentionally precedes active row.
}
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence; const timer = setTimeout(() => reject(Error(method)), 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value }
async function until(expression) { for (let i = 0; i < 300; i++) { if (await evaluate(expression)) return; await new Promise(r => setTimeout(r, 80)) } throw Error(JSON.stringify({ expression, body: await evaluate('document.body.innerText'), errors })) }
async function visit(path, text) { await command('Page.navigate', { url: origin + path }); await until(`document.body.innerText.includes(${JSON.stringify(text)})`) }
async function widths() { for (const width of [360, 768, 1440]) { await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 640 }); assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true, `width ${width}`) } }
ws.onmessage = async event => {
  const m = JSON.parse(event.data), item = pending.get(m.id)
  if (item) { clearTimeout(item.timer); pending.delete(m.id); m.error ? item.reject(Error(m.error.message)) : item.resolve(m.result) }
  if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.text)
  if (m.method !== 'Fetch.requestPaused') return
  const { requestId, request } = m.params, path = new URL(request.url).pathname
  try {
    assert.equal(request.method, 'GET', `Unexpected mutation ${path}`)
    let body
    const current = records().find(r => ['ACTIVE', 'PAUSED'].includes(r.status))
    if (path.endsWith('/auth/session')) body = { user, roles: ['CUSTOMER'] }
    else if (path.endsWith('/users/me')) body = user
    else if (path.endsWith('/memberships/me')) body = records()
    else if (path.endsWith('/profile/membership')) body = { membership_id: current?.id || null, plan_name: current?.terms_snapshot.name || null, status: current?.status || 'EXPIRED', start_date: current?.start_at || null, end_date: current?.end_at || null, membership_scope: 'MULTI_GYM', active_gyms: [], membership_features: [] }
    else if (path.endsWith('/customer/access-calendar')) body = { access_type: 'MULTI_GYM', gym: null, days: [{ date: '2026-11-12', status: 'TODAY', qr_status: current?.status === 'ACTIVE' ? 'ACTIVE' : current?.status === 'PAUSED' ? 'PAUSED' : 'NO_ACCESS', qr_available: current?.status === 'ACTIVE', gym_name: null, checkin_time: null }] }
    else if (/\/memberships\/me\/\d+\/pause$/.test(path)) {
      const id = Number(path.split('/').at(-2)); pauseReads.push(id)
      const row = [active, expired, cancelled, paused].find(r => r.id === id)
      body = { membership_id: id, membership_status: row.status, pause_allowed: false, can_pause: false, max_pause_days: 0, pause_days_used: 0, pause_days_remaining: 0, currently_paused: row.status === 'PAUSED', eligible_from: null, eligible_until: null, original_end_at: row.end_at, current_end_at: row.end_at, current_pause: null, history: [], reason_code: 'PAUSE_NOT_ALLOWED', timezone: 'Asia/Kolkata' }
    } else throw Error(`Unexpected API ${path}`)
    await command('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') })
  } catch (error) { errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }).catch(() => {}) }
}
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: "localStorage.setItem('fitigo:access_token','membership-history-fixture')" })
  await visit('/membership', 'Current monthly plan'); await until("document.body.innerText.includes('Generate Visit QR')")
  assert.equal(await evaluate("document.querySelector('.fm-membership-history').open"), false)
  assert.equal(await evaluate("document.body.innerText.includes('Previous expired plan')"), false)
  assert.equal(await evaluate("document.querySelectorAll('.fm-pause-section').length"), 1)
  assert.equal(pauseReads.some(id => [1, 3].includes(id)), false)
  await widths()
  // Native disclosure must work with keyboard, not only programmatic clicks.
  await command('Page.bringToFront')
  await evaluate("document.querySelector('.fm-history-toggle').focus()")
  assert.equal(await evaluate("document.activeElement === document.querySelector('.fm-history-toggle')"), true)
  await command('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', text: '\r', windowsVirtualKeyCode: 13 })
  await command('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
  await until("document.body.innerText.includes('Previous expired plan') && document.body.innerText.includes('Cancelled old plan')")
  assert.equal(await evaluate("document.querySelector('.fm-membership-history').open"), true)
  assert.equal(await evaluate("!!document.querySelector('.fm-history-records a[href=\"/profile/visits\"]')"), true)
  await until("document.querySelectorAll('.fm-pause-section').length === 3"); await widths()
  await evaluate("document.querySelector('.fm-history-toggle').click()")
  await until("!document.querySelector('.fm-membership-history').open && !document.querySelector('.fm-history-records')")
  assert.equal(await evaluate("document.body.innerText.includes('Previous expired plan')"), false)
  await visit('/membership/1/details', 'Previous expired plan')
  assert.equal(await evaluate("!!document.querySelector('.fm-membership-history')"), false)
  mode = 'history-only'; await visit('/membership', 'Your next chapter starts here')
  assert.equal(await evaluate("document.querySelector('.fm-membership-history').open"), false)
  assert.equal(await evaluate("!!document.querySelector('.fm-current-access')"), false)
  await evaluate("document.querySelector('.fm-history-toggle').click()")
  await until("document.body.innerText.includes('Previous expired plan')"); await widths()
  mode = 'paused'; await visit('/membership', 'Paused current plan')
  assert.equal(await evaluate("document.body.innerText.includes('Previous expired plan')"), false)
  mode = 'only-current'; await visit('/membership', 'Current monthly plan')
  assert.equal(await evaluate("!!document.querySelector('.fm-membership-history')"), false)
  mode = 'empty'; await visit('/membership', 'Your next chapter starts here')
  assert.equal(await evaluate("!!document.querySelector('.fm-membership-history')"), false)
  assert.deepEqual(errors, [])
  console.log('PASS current membership only by default; keyboard history expand/collapse; lazy historical pause cards; details preserved; paused/history-only/empty states; 360/768/1440 layouts; no mutations')
} finally { await command('Fetch.disable').catch(() => {}); ws.close(); await target.dispose() }