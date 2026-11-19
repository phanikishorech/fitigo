// Mocked business APIs, isolated Chrome storage. Never changes real membership or money.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
const pending = new Map(), errors = []
let seq = 0, eligible = true, cancelled = false, cancelFailure = false, transferred = false, kind = 'MULTI_GYM', recipient = false, transferFailure = false, transferKeys = [], cancelCalls = 0
const user = { id: 1, email: 'fixture@example.com', first_name: 'Policy', last_name: 'Fixture', status: 'ACTIVE' }
const policy = () => ({ eligible: eligible && !cancelled, reason: eligible ? 'Cancellation is available.' : 'Cancellation is unavailable within 3 hours of the scheduled booking.', policy: 'Cancel at least 3 hours before the scheduled start. Eligible amounts go to FitiGo Wallet.', deadline: '2027-01-03T15:00:00+05:30', scheduled_start: '2027-01-03T18:00:00+05:30', refundable_amount: '100.00', currency: 'INR', wallet_credit_amount: cancelled ? '100.00' : '0.00', wallet_transaction_id: cancelled ? 9 : null, cancelled_at: cancelled ? '2027-01-03T14:00:00+05:30' : null, cancellation_reason: cancelled ? 'Plans changed' : null })
const transfer = () => ({ eligible: kind === 'MULTI_GYM' && !transferred, reason: transferred ? 'Already transferred once.' : kind === 'SINGLE_GYM' ? 'Single-Gym memberships cannot be transferred.' : null, status: transferred && !recipient ? 'TRANSFERRED' : 'ACTIVE', cancel_allowed: false, remaining_valid_until: '2027-02-01T12:00:00+05:30', history: transferred ? { reference: 'fixture-transfer', status: 'COMPLETED', direction: recipient ? 'RECEIVED' : 'SENT', transferred_at: '2027-01-03T14:00:00+05:30' } : null })
const member = () => ({ id: 1, user_id: recipient ? 2 : 1, gym_id: kind === 'SINGLE_GYM' ? 1 : null, plan_id: kind === 'SINGLE_GYM' ? 1 : null, membership_type: kind, status: transfer().status, start_at: '2027-01-01T12:00:00+05:30', end_at: '2027-02-01T12:00:00+05:30', paid_amount: '100', currency: 'INR', payment_provider: 'WALLET', payment_status: 'PAID', terms_snapshot: { name: 'Fixture Multi-Gym', duration_value: 1, duration_unit: 'MONTH' }, transfer: transfer() })
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++seq, timer = setTimeout(() => reject(Error(method)), 15000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const response = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (response.exceptionDetails) throw Error(response.exceptionDetails.exception?.description); return response.result.value }
async function until(expression) { for (let i = 0; i < 180; i++) { if (await evaluate(`Boolean(${expression})`)) return; await new Promise(resolve => setTimeout(resolve, 70)) } throw Error(JSON.stringify({ expression, body: await evaluate('document.body.innerText'), errors })) }
async function click(text, selector = 'button') { const expression = `Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(el=>el.textContent.trim()===${JSON.stringify(text)})`; await until(expression); await evaluate(`${expression}.click()`) }
async function page(path, text) { await command('Page.navigate', { url: 'http://127.0.0.1:5173' + path }); await until(`document.body.innerText.includes(${JSON.stringify(text)})`) }
async function layouts() { for (const width of [360, 768, 1440]) { await command('Emulation.setDeviceMetricsOverride', { width, height: 950, deviceScaleFactor: 1, mobile: width < 640 }); assert.equal(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'), true) } }
ws.onmessage = async event => {
  const message = JSON.parse(event.data), item = pending.get(message.id)
  if (item) { pending.delete(message.id); clearTimeout(item.timer); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result) }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.exception?.description)
  if (message.method !== 'Fetch.requestPaused') return
  const { request, requestId } = message.params, path = new URL(request.url).pathname
  let body = {}, status = 200
  if (path.endsWith('/auth/session')) body = { user, roles: ['CUSTOMER'] }
  else if (path.endsWith('/users/me')) body = user
  else if (path.endsWith('/cart/summary')) body = { count: 0 }
  else if (path.endsWith('/notifications/inbox')) body = { enabled: true, items: [], total: 0, unread_count: 0 }
  else if (path.endsWith('/profile/bookings')) body = [{ booking_id: 1, booking_status: cancelled ? 'CANCELLED' : 'CONFIRMED', attendance_status: null, gym_id: 1, gym_name: 'Policy gym', access_type: 'Gym access', visit_date: '2027-01-03', start_time: '18:00:00', end_time: '19:00:00', membership_covered: false, amount_paid: '100', currency: 'INR', cancellation: policy() }]
  else if (path.endsWith('/bookings/1/cancel')) { cancelCalls++; if (cancelFailure) { status = 409; body = { detail: 'Fixture cutoff conflict. No credit was issued.' } } else { cancelled = true; body = { id: 1, currency: 'INR', cancellation: policy() } } }
  else if (path.endsWith('/memberships/me')) body = [member()]
  else if (path.endsWith('/profile/membership')) body = { membership_id: transferred && !recipient ? null : 1, status: transferred && !recipient ? null : 'ACTIVE', plan_name: 'Fixture Multi-Gym', start_date: member().start_at, end_date: member().end_at, membership_scope: kind, active_gyms: [], membership_features: [] }
  else if (path.endsWith('/customer/access-calendar')) body = { access_type: kind, gym: kind === 'SINGLE_GYM' ? { id: 1, name: 'Policy gym' } : null, days: [{ date: '2027-01-03', status: 'TODAY', qr_available: !transferred || recipient, qr_status: transferred && !recipient ? 'NO_ACCESS' : 'ACTIVE' }] }
  else if (path.endsWith('/memberships/me/1/pause')) body = { membership_id: 1, membership_status: 'ACTIVE', pause_allowed: false, can_pause: false, max_pause_days: 0, pause_days_used: 0, pause_days_remaining: 0, currently_paused: false, original_end_at: member().end_at, current_end_at: member().end_at, history: [], reason_code: 'PAUSE_NOT_ALLOWED' }
  else if (path.endsWith('/memberships/me/1/transfer/preview')) body = { recipient_name: 'Recipient F.', verified_email: JSON.parse(request.postData).recipient_email, confirmation_token: 'fixture-confirmation-token', valid_until: member().end_at, message: 'One permanent transfer. Dates and pauses stay unchanged.' }
  else if (path.endsWith('/memberships/me/1/transfer')) { transferKeys.push(Object.entries(request.headers).find(([name]) => name.toLowerCase() === 'idempotency-key')?.[1]); assert.equal(JSON.parse(request.postData).confirmed, true); if (transferFailure) { status = 409; body = { detail: 'Fixture transfer conflict. Ownership unchanged.' } } else { transferred = true; body = { status: 'COMPLETED', reference: 'fixture-transfer' } } }
  else if (path.endsWith('/gyms/1/details')) body = { gym_id: 1, gym_name: 'Policy gym', images: [], location: {}, ratings: {}, opening_hours: { weekly: [] }, rules: [], important_information: [], membership_access: {}, amenities: [], classes_nearby: [], reviews: [] }
  else if (path.endsWith('/memberships/gyms/1/plans')) body = [{ id: 1, name: 'Single plan', duration_days: 30, price: '100', currency: 'INR' }]
  else { errors.push('Unexpected API: ' + path); status = 404 }
  await command('Fetch.fulfillRequest', { requestId, responseCode: status, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') }).catch(() => {})
}
try {
  await command('Page.enable'); await command('Runtime.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: "localStorage.setItem('fitigo:access_token','policy-fixture')" })
  await page('/bookings', 'Cancel Booking'); await click('Cancel Booking'); await until("!!document.querySelector('dialog[open]')"); await layouts()
  assert.equal(cancelCalls, 0); assert.ok(await evaluate("document.querySelector('dialog').innerText.includes('not your original payment method')"))
  cancelFailure = true; await click('Confirm cancellation'); await until("document.body.innerText.includes('Fixture cutoff conflict')"); assert.equal(cancelled, false)
  cancelFailure = false; await click('Confirm cancellation'); await until("document.body.innerText.includes('Wallet transaction #9')")
  eligible = false; cancelled = false; await page('/bookings', 'Cancellation is unavailable within 3 hours')
  assert.equal(await evaluate("Array.from(document.querySelectorAll('button')).some(el=>el.textContent==='Cancel Booking')"), false)
  await page('/membership/1/details', 'Transfer Membership'); await click('Transfer Membership'); await until("!!document.querySelector('dialog[open]')")
  await evaluate("(()=>{const el=document.querySelector('dialog input[type=email]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'recipient@example.com');el.dispatchEvent(new Event('input',{bubbles:true}))})()")
  await click('Check recipient'); await until("document.body.innerText.includes('Recipient F.')")
  assert.equal(await evaluate("Array.from(document.querySelectorAll('button')).find(el=>el.textContent==='Confirm permanent transfer').disabled"), true)
  await layouts(); await evaluate("document.querySelector('dialog input[type=checkbox]').click()")
  transferFailure = true; await click('Confirm permanent transfer'); await until("document.body.innerText.includes('Fixture transfer conflict')"); assert.equal(transferred, false)
  transferFailure = false; await click('Confirm permanent transfer'); await until("document.body.innerText.includes('Transferred — you no longer own')")
  assert.ok(transferKeys[0]); assert.equal(transferKeys[0], transferKeys[1])
  recipient = true; await page('/membership/1/details', 'Received by transfer'); assert.equal(await evaluate("Array.from(document.querySelectorAll('button')).some(el=>el.textContent==='Transfer Membership')"), false)
  transferred = false; recipient = false; kind = 'SINGLE_GYM'; await page('/membership/1/details', 'Single-Gym Access')
  assert.equal(await evaluate("Array.from(document.querySelectorAll('button')).some(el=>/Transfer Membership|Cancel Membership/.test(el.textContent))"), false)
  assert.deepEqual(errors, [])
  console.log('PASS: backend-driven cancellation/denial/deadline, wallet confirmation and conflict; explicit one-time transfer with stable retry key, transferred ownership views, Single-Gym restrictions; dialogs at 360/768/1440px.')
} finally { await command('Fetch.disable').catch(() => {}); for (const item of pending.values()) clearTimeout(item.timer); ws.close(); await target.dispose() }