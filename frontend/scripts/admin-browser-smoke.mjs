// Live read-only business-data checks. Only login/logout sessions are changed.
// Uses the existing Chrome CDP setup; no API interception or fake dashboard data.
import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const sourceLabel = process.env.FITIGO_FIXTURE_MODE === '1' ? 'test-fixture' : 'live API'
const targets = await (await fetch('http://localhost:9231/json')).json()
const ws = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0; const pending = new Map(); const exceptions = []
ws.onmessage = event => {
  const message = JSON.parse(event.data)
  if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails.text)
  if (message.id && pending.has(message.id)) { const item = pending.get(message.id); clearTimeout(item.timer); pending.delete(message.id); message.error ? item.reject(new Error(message.error.message)) : item.resolve(message.result) }
}
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence; const timer = setTimeout(() => reject(new Error(`Timeout: ${method}`)), 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const result = await command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (result.exceptionDetails) throw new Error(result.exceptionDetails.text); return result.result.value }
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until(expression) { for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await wait(150) } throw new Error(`Not ready: ${expression}; page: ${await evaluate('document.body.innerText.slice(0,600)')}`) }
async function visit(path, text) { await command('Page.navigate', { url: origin + path }); await until(`document.body.innerText.includes(${JSON.stringify(text)})`); await until(`!document.querySelector('[aria-label="Loading"]')`) }
async function width(value) { await command('Emulation.setDeviceMetricsOverride', { width: value, height: 1000, deviceScaleFactor: 1, mobile: value < 640 }); await wait(60); const size = await evaluate('({client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth})'); assert.ok(size.scroll <= size.client + 1, `Overflow at ${value}: ${JSON.stringify(size)}`) }
async function fill(selector, value) { await evaluate(`(() => {const el=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('input',{bubbles:true}));})()`); await wait(50) }
async function click(text, selector = 'button') { await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(el=>el.textContent.trim()===${JSON.stringify(text)}).click()`); await wait(100) }
async function screenshot(name) { const shot = await command('Page.captureScreenshot', { format: 'png' }); await writeFile(join(tmpdir(), name), Buffer.from(shot.data, 'base64')) }
try {
  await command('Runtime.enable'); await command('Page.enable')
  await visit('/admin/login', 'Welcome back')
  await evaluate(`localStorage.removeItem('fitigo:access_token');localStorage.removeItem('fitigo:refresh_token')`)
  for (const value of [360,390,430,768,1024,1280,1440,1920]) await width(value)
  await screenshot('fitigo-admin-login.png')
  await visit('/admin/users', 'Welcome back'); assert.equal(await evaluate('location.pathname'), '/admin/login')
  await visit('/admin/access-denied', 'Access denied'); await width(360)
  await visit('/admin/session-expired', 'Your session has expired.')
  console.log('PASS login, protected-route redirect, denied/expired states and 8 viewport widths')
  if (process.env.FITIGO_TEST_EMAIL && process.env.FITIGO_TEST_PASSWORD) {
    await visit('/admin/login', 'Welcome back')
    await fill('input[name="email"]', process.env.FITIGO_TEST_EMAIL); await fill('input[name="password"]', process.env.FITIGO_TEST_PASSWORD)
    await evaluate(`document.querySelector('form').requestSubmit()`)
    await until(`location.pathname==='/admin/dashboard'`); await until(`document.querySelectorAll('.ad-metric').length===4`); await until(`!document.querySelector('[aria-label="Loading"]')`)
    for (const value of [360,390,430,768,1024,1280,1440,1920]) await width(value)
    await width(1440); await screenshot('fitigo-admin-dashboard-desktop.png'); await width(390); await screenshot('fitigo-admin-dashboard-mobile.png')
    await evaluate(`document.querySelector('[aria-label="Open navigation"]').click()`); await until(`!!document.querySelector('dialog[open]')`)
    await command('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }); await until(`!document.querySelector('dialog[open]')`)
    console.log(`PASS ${sourceLabel} dashboard, responsive layout, mobile drawer and Escape dismissal`)
    for (const [path,text] of [['/admin/users','Manage FitiGo platform users.'],['/admin/gyms','Manage and review gyms'],['/admin/bookings','Manage bookings across FitiGo.'],['/admin/reports','Daily booking report'],['/admin/notifications','Notifications'],['/admin/profile','Admin profile']]) {
      await visit(path,text); await width(360); await width(1440)
      assert.equal(await evaluate(`document.querySelector('main')?.innerText.includes('Unable to load this view')`), false, path)
    }
    await visit('/admin/users','Manage FitiGo platform users.'); const userPath = await evaluate(`document.querySelector('main a[href^="/admin/users/"]')?.getAttribute('href')`)
    if (userPath) { await visit(userPath,'Account information'); await click('Deactivate user'); await until(`!!document.querySelector('dialog[open]')`); await width(360); await click('Keep unchanged','dialog button'); }
    await visit('/admin/gyms','Manage and review gyms'); const gymPath = await evaluate(`document.querySelector('main a[href^="/admin/gyms/"]')?.getAttribute('href')`)
    if (gymPath) { await visit(gymPath,'Gym information'); await click('Reject Gym'); await until(`!!document.querySelector('dialog[open]')`); await width(360); await click('Keep unchanged','dialog button'); }
    await visit('/admin/bookings','Manage bookings across FitiGo.'); const bookingPath = await evaluate(`document.querySelector('main a[href^="/admin/bookings/"]')?.getAttribute('href')`)
    if (bookingPath) { await visit(bookingPath,'Booking information'); await click('Force Cancel Booking'); await until(`!!document.querySelector('dialog[open]')`); await width(360); await click('Keep unchanged','dialog button'); }
    console.log(`PASS ${sourceLabel} lists, available record details and non-mutating confirmation dialogs`)
    await visit('/admin/users?status=ACTIVE','Manage FitiGo platform users.'); await fill('main input[type="search"]','no-match-admin-qa-987654321'); await until(`location.search.includes('q=no-match-admin-qa-987654321')`); assert.equal(await evaluate(`new URLSearchParams(location.search).get('status')`),'ACTIVE'); await until(`document.body.innerText.includes('No users found.')`)
    await visit('/admin/not-real','Page not found'); await width(360)
    await visit('/admin/dashboard','Platform overview and activity'); await width(1440); await click('Logout'); await until(`!!document.querySelector('dialog[open]')`); await click('Sign out','dialog button'); await until(`location.pathname==='/admin/login'`)
    assert.equal(await evaluate(`localStorage.getItem('fitigo:access_token')`),null)
    console.log('PASS debounced server search, preserved filters, empty state, 404 and logout')
  } else console.log('SKIP authenticated checks: set FITIGO_TEST_EMAIL and FITIGO_TEST_PASSWORD')
  assert.deepEqual(exceptions, []); console.log('PASS no unhandled browser exceptions')
} finally { ws.close() }