// Both portals, isolated fixture data only. Run with Chrome CDP on port 9231.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'

const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
for (const role of ['GYM_OWNER', 'ADMIN']) {
  const portal = role === 'ADMIN' ? 'admin' : 'owner'
  const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
  let sequence = 0, delayed = ''
  const pending = new Map(), calls = [], errors = []
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
    for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await wait(70) }
    throw Error(`${role}: ${expression}; ${await evaluate('document.body.innerText')}; ${errors}`)
  }
  const user = { id: 1, first_name: 'Range', last_name: 'Tester', email: 'ranges@example.test' }
  const gyms = [1, 2].map(id => ({ id, name: `Gym ${id}`, status: 'APPROVED', is_active: true, images: [], operating_hours: [] }))
  function fixture(url) {
    const path = url.pathname, query = url.searchParams
    if (path.endsWith('/auth/session')) return { user, roles: [role] }
    if (path.endsWith('/users/me')) return user
    if (path.endsWith('/users/me/roles')) return [role]
    if (path.endsWith('/admin/ping')) return { status: 'ok' }
    if (path.endsWith('/gym-owner/gyms')) return gyms
    if (path.endsWith('/admin/gyms')) return []
    if (path.endsWith('/dashboard/summary')) {
      const days = (Date.parse(query.get('date_to')) - Date.parse(query.get('date_from'))) / 86400000 + 1
      return { users: { total: 100, in_period: days }, gyms: { total: 2, in_period: days, pending_approval: 0 },
        bookings: { in_period: days, confirmed_in_period: days }, revenue: { in_period: String(days * 100), currency: 'INR' },
        visits: { fitigo_member: days, single_gym_membership: days, individual_booking: days, total: days * 3 } }
    }
    if (path.endsWith('/reports/bookings/daily')) {
      const rows = [], end = Date.parse(query.get('date_to'))
      for (let day = Date.parse(query.get('date_from')); day <= end; day += 86400000) rows.push({ day: new Date(day).toISOString().slice(0, 10), total_bookings: 1 })
      return rows
    }
    if (path.endsWith('/attendance') || path.endsWith('/bookings')) return []
    if (/\/gym-owner\/gyms\/\d+$/.test(path)) return gyms[Number(path.split('/').at(-1)) - 1]
    throw Error(`Unexpected ${path}`)
  }
  ws.onmessage = async event => {
    const message = JSON.parse(event.data), item = pending.get(message.id)
    if (item) { clearTimeout(item.timer); pending.delete(message.id); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result) }
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
    if (message.method === 'Fetch.requestPaused') {
      const { requestId, request } = message.params, url = new URL(request.url)
      calls.push(url)
      try {
        const body = fixture(url)
        if (delayed && url.searchParams.get('date_from') === delayed) await wait(600)
        await command('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') })
      } catch (error) { errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
    }
  }
  async function click(label) { await evaluate(`Array.from(document.querySelectorAll('main button')).find(el=>el.textContent.trim()===${JSON.stringify(label)}).click()`); await wait(100) }
  async function fill(label, value) { await evaluate(`(() => { const el=document.querySelector('input[aria-label="${label}"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'${value}');el.dispatchEvent(new Event('input',{bubbles:true})) })()`); await wait(60) }
  const metric = portal === 'admin' ? `document.querySelector('.ad-metric strong')?.textContent` : `document.querySelector('.ow-metric strong')?.textContent`
  try {
    await command('Runtime.enable'); await command('Page.enable')
    await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
    await command('Page.addScriptToEvaluateOnNewDocument', { source: "localStorage.setItem('fitigo:access_token','isolated-ranges-fixture')" })
    await command('Page.navigate', { url: `${origin}/${portal}/dashboard` })
    await until(`${metric}==='1'`)
    const today = calls.find(url => url.pathname.endsWith('/dashboard/summary')).searchParams.get('date_to')
    const day = new Date(`${today}T00:00:00Z`)
    const shift = n => new Date(day.getTime() - n * 86400000).toISOString().slice(0, 10)
    for (const [label, start, end] of [['Yesterday', shift(1), shift(1)], ['This week', shift((day.getUTCDay() + 6) % 7), today], ['This month', `${today.slice(0, 7)}-01`, today], ['Last 30 days', shift(29), today], ['Today', today, today]]) {
      const before = calls.length
      await click(label)
      await until(`${metric}===${JSON.stringify(String((Date.parse(end) - Date.parse(start)) / 86400000 + 1))}`)
      const requests = calls.slice(before).filter(url => url.searchParams.has('date_from'))
      assert.ok(requests.some(url => url.pathname.endsWith('/dashboard/summary')))
      assert.ok(requests.every(url => url.searchParams.get('date_from') === start && url.searchParams.get('date_to') === end))
    }
    await click('Custom')
    const beforeInvalid = calls.length
    await fill('Start date', '2026-10-20'); await fill('End date', '2026-10-01')
    assert.equal(await evaluate(`document.querySelector('.fg-date-custom button').disabled`), true)
    assert.equal(calls.length, beforeInvalid)
    await fill('Start date', '2025-01-01'); await fill('End date', '2026-01-02')
    assert.ok(await evaluate(`document.body.innerText.includes('at most 366 days')`))
    await fill('Start date', '2026-09-01'); await fill('End date', '2026-09-03'); await click('Apply range')
    await until(`${metric}==='3'`)
    if (portal === 'owner') {
      await evaluate(`(() => {const el=document.querySelector('select[aria-label="Selected gym"]');el.value='2';el.dispatchEvent(new Event('change',{bubbles:true}))})()`)
      await wait(150)
      assert.equal(await evaluate(`document.querySelector('input[aria-label="Start date"]').value`), '2026-09-01')
      assert.ok(calls.some(url => url.searchParams.get('gym_id') === '2' && url.searchParams.get('date_from') === '2026-09-01'))
    }
    delayed = '2026-09-01'
    await fill('End date', '2026-09-04'); await click('Apply range'); await click('Today'); await wait(800)
    assert.equal(await evaluate(metric), '1')
    delayed = ''
    await click('Custom'); await fill('Start date', '2024-01-01'); await fill('End date', '2024-12-31'); await click('Apply range')
    await until(`${metric}==='366'`)
    for (const width of [360, 390, 768, 1440]) {
      await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 640 }); await wait(80)
      assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true, `${role}: overflow ${width}`)
    }
    const link = await evaluate(`Array.from(document.querySelectorAll('main a')).find(el=>el.getAttribute('href')?.startsWith('/${portal}/bookings?')).getAttribute('href')`)
    assert.ok(link.includes('date_from=2024-01-01&date_to=2024-12-31'))
    await command('Page.navigate', { url: origin + link }); await wait(600)
    const lastBookings = calls.filter(url => url.pathname.endsWith('/bookings')).at(-1)
    assert.equal(lastBookings.searchParams.get('date_from'), '2024-01-01')
    assert.equal(lastBookings.searchParams.get('date_to'), '2024-12-31')
    assert.deepEqual(errors, [])
    console.log(`PASS ${role}: all presets, custom validation/apply, stale responses, leap-year chart, responsive layout, booking drill-down${portal === 'owner' ? ', gym range preservation' : ''}`)
  } finally { ws.close(); await target.dispose() }
}