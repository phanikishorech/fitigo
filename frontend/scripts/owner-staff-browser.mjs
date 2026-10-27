// Isolated HTTP fixtures; never reads or removes real staff assignments.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, removed = false, fail = false
const pending = new Map(), errors = []
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 15000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw Error(result.exceptionDetails.text); return result.result.value }
async function until(expression) { for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await wait(80) } throw Error(`${expression}: ${await evaluate('document.body.innerText')}`) }
const staff = { id: 393, gym_id: 1, user_id: 6, role: 'STAFF', first_name: 'Kiran', last_name: 'Trainer', email: 'kiran.long.email.for.responsive.check@example.com', phone: '+919999999999', account_status: 'ACTIVE', assigned_at: '2026-10-27T10:30:00+05:30' }
function fixture(path, method) {
  if (path.endsWith('/auth/session')) return { user: { id: 1, first_name: 'Owner', email: 'owner@example.com' }, roles: ['GYM_OWNER'] }
  if (path.endsWith('/gym-owner/gyms')) return [{ id: 1, name: 'Assigned Gym', city: 'City', status: 'APPROVED', is_active: true }, { id: 2, name: 'Other Owned Gym', city: 'City', status: 'APPROVED', is_active: true }]
  if (path.endsWith('/gyms/1/staff')) return removed ? [] : [staff]
  if (path.endsWith('/gyms/2/staff')) return []
  if (path.endsWith('/gyms/1/staff/6') && method === 'DELETE') { removed = true; return { status: 'ok' } }
  throw Error(`Unexpected request ${method} ${path}`)
}
ws.onmessage = async event => {
  const message = JSON.parse(event.data), item = pending.get(message.id)
  if (item) { clearTimeout(item.timer); pending.delete(message.id); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result) }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
  if (message.method === 'Fetch.requestPaused') {
    const { requestId, request } = message.params, path = new URL(request.url).pathname
    try { const data = fixture(path, request.method); await command('Fetch.fulfillRequest', { requestId, responseCode: fail && path.endsWith('/staff') ? 503 : 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(data)).toString('base64') }) }
    catch (error) { errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
  }
}
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: "localStorage.setItem('fitigo:access_token','isolated-staff-fixture');localStorage.setItem('fitigo:owner:1:gym','1')" })
  await command('Page.navigate', { url: `${origin}/owner/staff` })
  await until(`document.body.innerText.includes('Kiran Trainer')`)
  for (const value of [staff.email, staff.phone, 'Account status', 'Access assigned']) assert.ok(await evaluate(`document.body.innerText.includes(${JSON.stringify(value)})`))
  assert.equal(await evaluate(`document.body.innerText.includes('Only staff IDs')`), false)
  await evaluate(`document.querySelector('main a[href="/owner/staff/6"]').click()`)
  await until(`location.pathname==='/owner/staff/6' && document.querySelector('main h1')?.textContent==='Kiran Trainer'`)
  for (const width of [360, 390, 768, 1440]) { await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 640 }); await wait(80); assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'), true, `Overflow ${width}`) }
  await evaluate(`Array.from(document.querySelectorAll('main button')).find(b=>b.textContent==='Remove access').click()`)
  await until(`!!document.querySelector('dialog[open]')`)
  assert.ok(await evaluate(`document.querySelector('dialog[open]').innerText.includes('Kiran Trainer') && document.querySelector('dialog[open]').innerText.includes(${JSON.stringify(staff.email)})`))
  await evaluate(`Array.from(document.querySelectorAll('dialog[open] button')).find(b=>b.textContent==='Keep unchanged').click()`)
  assert.equal(removed, false)
  await evaluate(`Array.from(document.querySelectorAll('main button')).find(b=>b.textContent==='Remove access').click()`)
  await evaluate(`Array.from(document.querySelectorAll('dialog[open] button')).find(b=>b.textContent==='Remove access').click()`)
  await until(`location.pathname==='/owner/staff' && document.body.innerText.includes('No staff members')`)
  assert.equal(removed, true)
  removed = false; fail = true
  await command('Page.navigate', { url: `${origin}/owner/staff` }); await until(`document.body.innerText.includes('Something went wrong')`)
  fail = false; await evaluate(`Array.from(document.querySelectorAll('main button')).find(b=>/try again/i.test(b.textContent)).click()`)
  await until(`document.body.innerText.includes('Kiran Trainer')`)
  await evaluate(`(() => {const el=document.querySelector('select[aria-label="Selected gym"]');el.value='2';el.dispatchEvent(new Event('change',{bubbles:true}))})()`)
  await until(`document.body.innerText.includes('No staff members')`)
  assert.equal(await evaluate(`document.querySelector('main').innerText.includes(${JSON.stringify(staff.email)})`), false)
  assert.deepEqual(errors, [])
  console.log('PASS owner staff identity list/detail, named removal confirmation/cancel, gym switching, error retry and 360–1440px layout')
} finally { ws.close(); await target.dispose() }