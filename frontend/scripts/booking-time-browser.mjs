// Isolated booking form fixture: intercept every API call, never writes live data.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const target = await isolatedBrowserTarget()
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, cartCalls = 0
const pending = new Map(), errors = []
const user = { id: 1, first_name: 'Test', last_name: 'Customer', email: 'time@example.test' }
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const response = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (response.exceptionDetails) throw Error(response.exceptionDetails.exception?.description); return response.result.value }
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until(expression) { for (let i = 0; i < 150; i++) { if (await evaluate(expression)) return; await wait(100) } throw Error(`Not ready: ${expression}; ${await evaluate('document.body.innerText')}`) }
async function input(selector, value) { await evaluate(`(()=>{const input=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,${JSON.stringify(value)});input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}))})()`); await wait(120) }
async function select(selector, value) { await evaluate(`(()=>{const input=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(input,${JSON.stringify(value)});input.dispatchEvent(new Event('change',{bubbles:true}))})()`); await wait(120) }
const add = `Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('Check availability & add to cart'))`
function fixture(path, request) {
  if (path.endsWith('/auth/session')) return { user, roles: ['CUSTOMER'] }
  if (path.endsWith('/users/me')) return user
  if (path.endsWith('/gyms/19/booking-options')) return { gym_id: 19, gym_name: 'Time Fixture Gym', gym_price_per_person: '100', has_classes: false, server_now: '2026-10-08T12:00:30+05:30', booking_timezone: 'Asia/Kolkata', membership_status: {}, available_access_types: [], workout_areas: [] }
  if (path.endsWith('/gyms/19/operating-hours')) return { gym_id: 19, date: '2026-10-08', day_of_week: 3, open_time: '06:00:00', close_time: '23:00:00', is_closed: false }
  if (path.endsWith('/cart/items/gym')) {
    cartCalls++; assert.equal(request.method, 'POST')
    assert.equal(JSON.parse(request.postData).preferred_start_time, '13:45')
    assert.equal(JSON.parse(request.postData).preferred_end_time, undefined)
    return { id: 1 }
  }
  if (path.endsWith('/cart/items')) return []
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
  await command('Emulation.setTimezoneOverride', { timezoneId: 'America/Los_Angeles' })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fitigo:access_token','isolated-time-fixture')` })
  await command('Page.navigate', { url: 'http://localhost:5173/gyms/19/book/schedule' })
  await until(`!!document.querySelector('select[aria-label="Start hour (IST)"]')`)
  await input('input[type="date"]', '2026-10-08')
  await until(`!!document.querySelector('select[aria-label="Start hour (IST)"]')`)
  assert.equal(await evaluate(`document.querySelector('input[type="date"]').min`), '2026-10-08')
  assert.equal(await evaluate(`!!document.querySelector('input[type="time"]')`), false)
  assert.equal(await evaluate(`Array.from(document.querySelector('select[aria-label="Start hour (IST)"]').options).some(o=>o.value==='11')`), false)
  await until(`${add}?.disabled === true`)
  assert.equal(cartCalls, 0)
  await input('input[type="date"]', '2026-10-07')
  await until(`${add}?.disabled === true`)
  await input('input[type="date"]', '2026-10-08')
  await until(`!!document.querySelector('select[aria-label="Start hour (IST)"]')`)
  await select('select[aria-label="Start hour (IST)"]', '12')
  assert.deepEqual(await evaluate(`Array.from(document.querySelector('select[aria-label="Start minutes"]').options).map(o=>o.value).filter(Boolean)`), ['15', '30', '45'])
  await select('select[aria-label="Start hour (IST)"]', '13')
  assert.deepEqual(await evaluate(`Array.from(document.querySelector('select[aria-label="Start minutes"]').options).map(o=>o.value).filter(Boolean)`), ['00', '15', '30', '45'])
  await select('select[aria-label="Start minutes"]', '45')
  await until(`document.body.innerText.includes('13:45–14:45 IST')`)
  await input('fieldset input', 'David')
  await until(`${add}?.disabled === false`)
  await evaluate(`${add}.click()`)
  await until(`location.pathname === '/cart'`)
  assert.equal(cartCalls, 1)
  assert.deepEqual(errors, [])
  console.log('PASS quarter-hour dropdowns, automatic one-hour end, past dates/times excluded, future visit uses original cart flow')
} finally { await command('Fetch.disable').catch(() => {}); ws.close(); await target.dispose() }