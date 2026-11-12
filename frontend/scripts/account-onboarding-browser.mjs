// TEST ONLY: isolated API fixtures; no real invitation, OTP or message delivery.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const target = await isolatedBrowserTarget()
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let id = 0, mode = 'new', failDelivery = true
const pending = new Map(), calls = [], errors = []
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
function command(method, params = {}) { return new Promise((resolve, reject) => { const key = ++id; pending.set(key, { resolve, reject }); ws.send(JSON.stringify({ id: key, method, params })) }) }
async function evaluate(expression) { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw Error(r.exceptionDetails.text); return r.result.value }
async function until(expression) { for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await wait(80) } throw Error(`Not ready: ${expression}; ${await evaluate('document.body.innerText')}`) }
async function fill(selector, value) { await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('input',{bubbles:true}))})()`); await wait(80) }
async function click(text) { await evaluate(`Array.from(document.querySelectorAll('button')).find(el=>el.textContent.trim()===${JSON.stringify(text)}).click()`); await wait(80) }
async function visit(path) { await command('Page.navigate', { url: 'about:blank' }); await wait(80); await command('Page.navigate', { url: origin + path }); await wait(200) }
ws.onmessage = async event => {
  const m = JSON.parse(event.data)
  if (pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(Error(m.error.message)) : p.resolve(m.result) }
  if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.text)
  if (m.method !== 'Fetch.requestPaused') return
  const { requestId, request } = m.params, path = new URL(request.url).pathname
  try {
    let body = {}, status = 200
    if (request.method === 'POST') calls.push({ path, body: JSON.parse(request.postData || '{}') })
    if (path.endsWith('/staff-invitations/inspect')) {
      body = { gym_name: 'Invitation Fixture Gym', expires_at: '2030-01-01T00:00:00Z', requires_current_password: mode === 'existing' }
      if (mode === 'expired') { status = 400; body = { detail: 'This invitation is invalid or expired. Ask the gym owner to resend it.' } }
    } else if (path.endsWith('/staff-invitations/accept')) body = { status: 'ACCEPTED' }
    else if (path.endsWith('/auth/email/send-otp')) {
      status = failDelivery ? 503 : 200
      body = failDelivery ? { code: 'ACCOUNT_DELIVERY_UNAVAILABLE' } : { status: 'ok', delivery_status: 'PROVIDER_ACCEPTED', resend_seconds: 60 }
    } else if (path.endsWith('/auth/email/verify-otp')) { status = 400; body = { detail: 'This verification code is invalid or expired. Request a new code.' } }
    else if (path.endsWith('/auth/password-reset/options')) body = { email_available: true, expiry_minutes: 15 }
    else if (path.endsWith('/auth/forgot-password')) { status = failDelivery ? 503 : 200; body = failDelivery ? { code: 'ACCOUNT_DELIVERY_FAILED' } : { delivery_status: 'PROVIDER_ACCEPTED' } }
    else if (path.endsWith('/facilities') || path.endsWith('/meta/gym-types')) body = []
    else if (path.endsWith('/gyms/discover')) body = { gyms: [], page: 1, page_size: 8, total_count: 0, has_more: false }
    else throw Error('Unexpected API '+path)
    await command('Fetch.fulfillRequest', { requestId, responseCode: status, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') })
  } catch (e) { errors.push(e.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
}
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  const token = 'isolated-invitation-fixture-not-a-real-credential'
  await visit('/auth/accept-invitation#token='+token)
  await until(`!!document.querySelector('form[aria-label="Accept staff invitation"]')`)
  assert.equal(await evaluate('location.hash'), '')
  assert.equal(await evaluate(`JSON.stringify(localStorage).includes(${JSON.stringify(token)}) || JSON.stringify(sessionStorage).includes(${JSON.stringify(token)})`), false)
  for (const width of [360, 768, 1440]) { await command('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 640 }); assert.equal(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'), true) }
  await fill('input[name="password"]', 'New Password 123!'); await fill('input[name="confirmation"]', 'Mismatch Password 123!')
  await click('Accept invitation'); await until(`document.body.innerText.includes('passwords do not match')`)
  assert.equal(calls.filter(c => c.path.endsWith('/accept')).length, 0)
  await fill('input[name="confirmation"]', 'New Password 123!'); await click('Accept invitation')
  await until(`document.body.innerText.includes('Invitation accepted.')`)
  assert.deepEqual(Object.keys(calls.at(-1).body).sort(), ['new_password', 'token'])
  mode = 'existing'; await visit('/auth/accept-invitation#token='+token)
  await until(`document.body.innerText.includes('Confirm your existing account password')`)
  assert.equal(await evaluate(`!!document.querySelector('input[name="confirmation"]')`), false)
  await fill('input[name="password"]', 'Existing Password 123!'); await click('Accept invitation')
  await until(`document.body.innerText.includes('Invitation accepted.')`)
  assert.deepEqual(Object.keys(calls.at(-1).body).sort(), ['current_password', 'token'])
  mode = 'expired'; await visit('/auth/accept-invitation#token='+token); await until(`document.body.innerText.includes('invalid or expired')`)
  await visit('/auth/login'); await until(`!!document.querySelector('[role="dialog"]')`)
  await fill('input[type="email"]', 'fixture@example.com')
  const send = await evaluate(`Array.from(document.querySelectorAll('button')).find(el=>/Send.*code|Send.*OTP/i.test(el.textContent))?.textContent.trim()`)
  assert.ok(send); await click(send)
  await until(`document.body.innerText.includes('not configured')`)
  assert.equal(await evaluate(`!!document.querySelector('[aria-label="OTP digit 1"]')`), false)
  failDelivery = false; await click(send); await until(`!!document.querySelector('[aria-label="OTP digit 1"]')`)
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('button')).find(el=>el.textContent.includes('Resend code')).disabled`), true)
  await visit('/auth/forgot-password'); await until(`!!document.querySelector('form[aria-label="Forgot password"]')`)
  failDelivery = true; await fill('input[name="email"]', 'fixture@example.com'); await click('Send reset link')
  await until(`document.body.innerText.includes('did not confirm')`)
  assert.equal(await evaluate(`document.body.innerText.includes('email provider accepted the request')`), false)
  assert.deepEqual(errors, [])
  console.log('PASS invitation new/existing/expired states, token URL cleanup, no role/gym payload, responsive layout, OTP/recovery delivery failures and resend cooldown')
} finally { await command('Fetch.disable').catch(() => {}); ws.close(); await target.dispose() }