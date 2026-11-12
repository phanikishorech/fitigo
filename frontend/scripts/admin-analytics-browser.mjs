// Isolated browser/API fixtures only. Never seeds or mutates working data.
import assert from 'node:assert/strict'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let seq = 0, mode = 'data'
const pending = new Map(), errors = [], requests = []
const user = { id: 3, first_name: 'Analytics', last_name: 'Admin', email: 'admin@example.test', status: 'ACTIVE', roles: ['ADMIN'] }
const metric = { bookings: 12, places: 18, confirmed: 8, pending: 1, cancelled: 2, expired: 1, attended: 5, no_show: 1,
  paid_bookings: 7, paid_amount: '1050.00', failed_payments: 1, refunded_payments: 1, review_required: 1, confirmation_rate: 66.67, cancellation_rate: 16.67 }
const zero = { ...metric, ...Object.fromEntries(Object.keys(metric).map(key => [key, key === 'paid_amount' ? '0' : 0])), confirmation_rate: null, cancellation_rate: null }
const options = Array.from({ length: 25 }, (_, i) => ({ id: i + 1, name: `Fitness Studio ${String(i + 1).padStart(2, '0')}`, country: 'India', state: i < 13 ? 'Telangana' : 'Karnataka', city: i < 13 ? 'Hyderabad' : 'Bengaluru' }))
function report(params) {
  const date_from = params.get('date_from'), date_to = params.get('date_to'), grain = params.get('grain')
  const gyms = options.filter(g => ['country', 'state', 'city'].every(k => !params.has(k) || params.get(k) === g[k]) && (!params.has('gym_id') || +params.get('gym_id') === g.id))
  const m = mode === 'empty' ? zero : metric
  return { date_from, date_to, grain, timezone: 'Asia/Kolkata', generated_at: '2026-11-12T12:00:00Z',
    scope: { mode: 'test', currency: 'INR', date_basis: 'SCHEDULED_BOOKING_DATE', basis: 'Verified gateway allocations. Not earned revenue; wallet and review-required amounts excluded.' },
    summary: { ...m, unique_customers: mode === 'empty' ? 0 : 6 }, previous: { ...zero, unique_customers: 0, date_from: '2026-09-14', date_to: '2026-10-13' },
    catalog: { gyms: gyms.length, active_gyms: gyms.length, gyms_with_bookings: mode === 'empty' ? 0 : 1 },
    gyms: gyms.map((g, i) => ({ ...g, ...(i === 0 ? m : zero), status: 'APPROVED', is_active: true, unique_customers: i === 0 && mode !== 'empty' ? 6 : 0 })),
    locations: [{ ...m, country: 'India', state: 'Telangana', city: 'Hyderabad', gyms: 13, active_gyms: 13 }, { ...zero, country: 'India', state: 'Karnataka', city: 'Bengaluru', gyms: 12, active_gyms: 12 }],
    series: [{ ...m, period: date_from, date_from, date_to }], options }
}
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++seq, timer = setTimeout(() => reject(Error(method)), 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value }
async function until(expression) { for (let i = 0; i < 250; i++) { if (await evaluate(expression)) return; await new Promise(r => setTimeout(r, 80)) } throw Error(JSON.stringify({ expression, body: await evaluate('document.body.innerText'), errors })) }
async function click(text) { await evaluate(`Array.from(document.querySelectorAll('main button')).find(b=>b.textContent.trim()===${JSON.stringify(text)}).click()`); await new Promise(r => setTimeout(r, 150)) }
async function select(label, value) { await evaluate(`(()=>{const el=Array.from(document.querySelectorAll('main label')).find(l=>l.querySelector('span')?.textContent===${JSON.stringify(label)}).querySelector('select');el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change',{bubbles:true}));})()`); await new Promise(r => setTimeout(r, 200)) }
ws.onmessage = async event => {
  const m = JSON.parse(event.data), item = pending.get(m.id)
  if (item) { clearTimeout(item.timer); pending.delete(m.id); m.error ? item.reject(Error(m.error.message)) : item.resolve(m.result) }
  if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.text)
  if (m.method !== 'Fetch.requestPaused') return
  const { requestId, request } = m.params
  try {
    assert.equal(request.method, 'GET', 'Analytics must not mutate data')
    const url = new URL(request.url), path = url.pathname
    let body, status = 200
    if (path.endsWith('/auth/session')) body = { user, roles: ['ADMIN'] }
    else if (path.endsWith('/users/me')) body = user
    else if (path.endsWith('/users/me/roles')) body = ['ADMIN']
    else if (path.endsWith('/admin/analytics')) {
      requests.push(Object.fromEntries(url.searchParams))
      if (mode === 'error' || mode === 'denied') { status = mode === 'error' ? 500 : 403; body = { detail: 'private SQL traceback' } }
      else body = report(url.searchParams)
    } else throw Error(`Unexpected API ${path}`)
    await command('Fetch.fulfillRequest', { requestId, responseCode: status, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') })
  } catch (error) {
    // StrictMode/filter switches abort obsolete GET requests intentionally.
    if (!/Invalid InterceptionId/.test(error.message)) errors.push(error.message)
    await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }).catch(() => {})
  }
}
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fitigo:access_token','isolated-analytics');window.analyticsExports=[];URL.createObjectURL=blob=>{window.analyticsExports.push(blob);return 'blob:fixture'};URL.revokeObjectURL=()=>{};HTMLAnchorElement.prototype.click=function(){if(!this.download)HTMLElement.prototype.click.call(this)}` })
  await command('Page.navigate', { url: origin + '/admin/analytics' })
  await until(`document.body.innerText.includes('Gym performance')`)
  assert.ok(await evaluate(`!!document.querySelector('nav a[href="/admin/analytics"][aria-current="page"]')`))
  await click('Next'); await until(`document.body.innerText.includes('Page 2 of 2')`)
  await click('Export CSV'); await until('window.analyticsExports.length===1')
  const csv = await evaluate('window.analyticsExports[0].text()')
  assert.equal(csv.split('\r\n').length, 26); assert.ok(csv.includes('SCHEDULED_BOOKING_DATE')); assert.ok(csv.includes('test'))
  await select('Group time by', 'week'); await until(`document.body.innerText.includes('week buckets')`)
  assert.equal(requests.at(-1).grain, 'week')
  await select('State', JSON.stringify('Telangana')); await until(`document.body.innerText.includes('13 rows')`)
  assert.equal(requests.at(-1).state, 'Telangana')
  await click('Location-wise'); await until(`document.body.innerText.includes('Location performance')`)
  await click('Time periods'); await until(`document.querySelector('table caption').textContent.includes('Time periods')`)
  await click('Gym-wise')
  const output = join(tmpdir(), 'fitigo-admin-analytics'); mkdirSync(output, { recursive: true })
  await evaluate('document.activeElement?.blur()')
  for (const width of [360, 768, 1440]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 1050, deviceScaleFactor: 1, mobile: width < 640 })
    assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true, `overflow at ${width}`)
    const shot = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
    writeFileSync(join(output, `analytics-${width}.png`), Buffer.from(shot.data, 'base64'))
  }
  await command('Page.bringToFront'); await command('Emulation.setFocusEmulationEnabled', { enabled: true })
  await evaluate(`document.querySelector('.aa-definitions summary').scrollIntoView({block:'center'});document.querySelector('.aa-definitions summary').focus()`)
  await command('Input.dispatchKeyEvent', { type: 'keyDown', key: ' ', code: 'Space', windowsVirtualKeyCode: 32, text: ' ' })
  await command('Input.dispatchKeyEvent', { type: 'keyUp', key: ' ', code: 'Space', windowsVirtualKeyCode: 32 })
  await until(`document.querySelector('.aa-definitions').open`)
  await click('Custom'); await until(`!!document.querySelector('input[aria-label="Start date"]')`)
  await evaluate(`(()=>{const el=document.querySelector('input[aria-label="Start date"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'2099-01-01');el.dispatchEvent(new Event('input',{bubbles:true}));})()`)
  await until(`document.body.innerText.includes('Start date must not be after end date')`)
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Apply range').disabled`), true)
  await click('Today')
  mode = 'empty'; await click('Refresh analytics'); await until(`document.body.innerText.includes('No bookings in this period')`)
  assert.ok(await evaluate(`document.body.innerText.includes('Fitness Studio 01')`))
  mode = 'error'; await click('Refresh analytics'); await until(`document.body.innerText.includes('Unable to load this view')`)
  assert.equal(await evaluate(`document.body.innerText.includes('private SQL')`), false)
  mode = 'denied'; await click('Try again'); await until(`document.body.innerText.includes('Access denied')`)
  mode = 'data'; await click('Try again'); await until(`document.body.innerText.includes('Gym performance')`)
  assert.deepEqual(errors, [])
  console.log('PASS analytics browser: filters/grains, tables/pagination, all-row CSV, invalid dates, empty/error/403, keyboard, 360/768/1440. Artifacts:', output)
} finally { ws.close(); await target.dispose() }