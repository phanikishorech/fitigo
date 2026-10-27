// Isolated HTTP fixtures: never reads or mutates real owner/customer data.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'

const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const target = await isolatedBrowserTarget()
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, delayGymOne = false, failGymTwo = false
const pending = new Map(), errors = [], calls = []
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
function command(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 15000)
    pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (result.exceptionDetails) throw Error(result.exceptionDetails.text)
  return result.result.value
}
async function until(expression) {
  for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await wait(80) }
  throw Error(`Not ready: ${expression}; ${await evaluate('document.body.innerText')}`)
}
const gyms = [1, 2].map(id => ({ id, name: `Fixture Gym ${id}`, city: 'Test City', status: 'APPROVED', is_active: true,
  created_at: '2026-10-01T00:00:00Z', images: [], operating_hours: [], facilities: [] }))
function fixture(path, query) {
  if (path.endsWith('/auth/session')) return { user: { id: 1, first_name: 'Owner', email: 'owner@example.test' }, roles: ['GYM_OWNER'] }
  if (path.endsWith('/users/me')) return { id: 1, first_name: 'Owner', email: 'owner@example.test' }
  if (path.endsWith('/users/me/roles')) return ['GYM_OWNER']
  if (path.endsWith('/gym-owner/gyms')) return gyms
  const gymId = Number(query.get('gym_id') || path.match(/\/gyms\/(\d+)/)?.[1] || 0)
  if (path.endsWith('/dashboard/summary')) {
    const count = query.get('date_from') === '2026-10-01' ? 0 : gymId === 1 ? 1 : gymId === 2 ? 2 : 3
    return { gym_id: gymId || null, date: query.get('date'), upcoming_visits: count * 2, generated_at: '2026-10-27T12:00:00+05:30',
      visits: { fitigo_member: count, single_gym_membership: count * 2, individual_booking: count * 3, total: count * 6 },
      gyms: { total: gymId ? 1 : 2, approved: gymId ? 1 : 2, draft: 0, pending_approval: 0 },
      bookings: { today: count, on_date: count, upcoming: count, in_period: count, confirmed_in_period: count },
      attendance: { upcoming: count, attended: count, cancelled: count, no_show: count, pending_payment: 0, expired: 0, unresolved: 0 },
      revenue: { mode: 'test', last_30d: String(count * 100), in_period: String(count * 100), currency: 'INR', single_gym_membership: String(count * 60), individual_booking: String(count * 40), total: String(count * 100), fully_refunded_sales: '0', partial_refund_count: 0, excluded_paid_records: 0 } }
  }
  if (path.endsWith('/attendance')) return query.get('date_from') === '2026-10-01' ? [] : [
    { id: `checkin:${gymId}`, gym_id: gymId, booking_id: null, category: 'fitigo_member', visits: 1,
      customer_name: `Member Gym ${gymId}`, recorded_at: '2026-10-19T12:00:00+05:30' },
    { id: `booking:${gymId}`, gym_id: gymId, booking_id: gymId, category: 'individual_booking', visits: 1,
      customer_name: `Visitor Gym ${gymId}`, recorded_at: '2026-10-19T11:00:00+05:30' }
  ]
  if (path.endsWith('/bookings')) return query.get('date_from') === '2026-10-01' ? [] : [{ id: gymId, gym_id: gymId,
    slot_date: query.get('date_from'), quantity: 1, total_price: '100', currency: 'INR', status: 'CONFIRMED',
    customer: { id: gymId, first_name: `Booking Gym ${gymId}` }, slot: { name: 'Visit', start_time: '10:00', end_time: '11:00' }, payment: null }]
  if (/\/gym-owner\/gyms\/\d+$/.test(path)) return gyms[gymId - 1]
  throw Error(`Unexpected API ${path}`)
}
ws.onmessage = async event => {
  const message = JSON.parse(event.data)
  if (pending.has(message.id)) {
    const item = pending.get(message.id); clearTimeout(item.timer); pending.delete(message.id)
    message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result)
  }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
  if (message.method === 'Fetch.requestPaused') {
    const { requestId, request } = message.params, url = new URL(request.url)
    calls.push(url.pathname + url.search)
    try {
      const body = fixture(url.pathname, url.searchParams)
      if (delayGymOne && (url.searchParams.get('gym_id') === '1' || url.pathname.includes('/gyms/1/'))) await wait(700)
      const failed = failGymTwo && url.searchParams.get('gym_id') === '2'
      await command('Fetch.fulfillRequest', { requestId, responseCode: failed ? 500 : 200,
        responseHeaders: [{ name: 'Content-Type', value: 'application/json' }],
        body: Buffer.from(JSON.stringify(failed ? { detail: 'Fixture summary failure' } : body)).toString('base64') })
    } catch (error) { errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
  }
}
const totals = `Array.from(document.querySelectorAll('.ow-metric')).filter(el=>el.querySelector('.ow-metric-top')?.textContent==='Visits completed').map(el=>el.querySelector('strong').textContent)`
async function selectGym(id) {
  await evaluate(`(() => { const el=document.querySelector('select[aria-label="Selected gym"]');el.value='${id}';el.dispatchEvent(new Event('change',{bubbles:true})) })()`)
}
try {
  await command('Runtime.enable'); await command('Page.enable')
  await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: "localStorage.setItem('fitigo:access_token','isolated-dashboard-fixture')" })
  await command('Page.navigate', { url: `${origin}/owner/dashboard` })
  await until(`JSON.stringify(${totals})==='["18","6"]'`)
  assert.equal(await evaluate(`document.querySelectorAll('main .ow-metric').length`), 6)
  assert.equal(await evaluate(`document.querySelectorAll('main table').length`), 0)
  assert.deepEqual(await evaluate(`Array.from(document.querySelectorAll('.ow-report-heading h2')).map(el=>el.textContent)`), ['Overall Metrics', 'Selected Gym'])
  const beforeExpand = calls.length
  await evaluate(`document.querySelectorAll('.ow-report-heading button')[0].click()`)
  assert.deepEqual(await evaluate(`Array.from(document.querySelectorAll('.ow-secondary-panel')).map(el=>el.hidden)`), [false, true])
  await evaluate(`document.querySelectorAll('.ow-report-heading button')[1].click()`)
  await evaluate(`document.querySelectorAll('.ow-report-heading button')[0].click()`)
  assert.deepEqual(await evaluate(`Array.from(document.querySelectorAll('.ow-secondary-panel')).map(el=>el.hidden)`), [true, false])
  assert.equal(calls.length, beforeExpand)
  const overallCalls = calls.filter(path => path.includes('/dashboard/summary') && !path.includes('gym_id=')).length
  await selectGym(2)
  await until(`JSON.stringify(${totals})==='["18","12"]'`)
  assert.equal(await evaluate(`document.querySelector('main').innerText.includes('Member Gym 1') || document.querySelector('main').innerText.includes('Booking Gym 1')`), false)
  assert.equal(calls.filter(path => path.includes('/dashboard/summary') && !path.includes('gym_id=')).length, overallCalls)
  delayGymOne = true
  await selectGym(1); await wait(100); await selectGym(2); await wait(900)
  assert.deepEqual(await evaluate(totals), ['18', '12'])
  assert.equal(await evaluate(`document.querySelector('main').innerText.includes('Member Gym 1')`), false)
  delayGymOne = false
  for (const width of [320, 360, 390, 768, 1024, 1440]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 640 })
    await wait(80)
    assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true, `Overflow at ${width}`)
  }
  await evaluate(`Array.from(document.querySelectorAll('.fg-date-presets button')).find(el=>el.textContent==='Custom').click()`)
  for (const label of ['Start date', 'End date']) await evaluate(`(() => {const el=document.querySelector('input[aria-label="${label}"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'2026-10-01');el.dispatchEvent(new Event('input',{bubbles:true}))})()`)
  await evaluate(`document.querySelector('.fg-date-custom button').click()`)
  await until(`JSON.stringify(${totals})==='["0","0"]'`)
  assert.equal(calls.some(path => /\/(bookings|attendance)\?/.test(path)), false)
  failGymTwo = true
  await selectGym(1); await until(`document.body.innerText.includes('Fixture Gym 1') && ${totals}.length===2`)
  await selectGym(2); await until(`document.querySelector('main').innerText.includes('Something went wrong')`)
  assert.deepEqual(await evaluate(totals), ['0'])
  failGymTwo = false
  await evaluate(`Array.from(document.querySelectorAll('main button')).find(el=>/try again/i.test(el.textContent)).click()`)
  await until(`${totals}.length===2`)
  assert.deepEqual(errors, [])
  console.log('PASS compact dashboard: six primary cards, independent expansion/collapse without requests, no tables, scope/date/error recovery and responsive layout')
} finally { ws.close(); await target.dispose() }