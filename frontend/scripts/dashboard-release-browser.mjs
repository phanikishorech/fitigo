// Working API GETs only. Authentication bootstrap reads the local DB; never logs credentials.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { writeFileSync } from 'node:fs'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const token = execFileSync(fileURLToPath(new URL('../../backend/.venv/Scripts/python.exe', import.meta.url)), ['-B', '-c', `
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from app.database.session import engine
from app.models.auth import User,Role,UserRole
from app.core.security import create_access_token
with engine.connect() as c:
 c.execute(text('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY'))
 with Session(bind=c,autoflush=False) as db:
  u=db.scalar(select(User).join(UserRole,UserRole.user_id==User.id).join(Role,Role.id==UserRole.role_id).where(Role.name.in_(['ADMIN','SUPER_ADMIN']),User.status=='ACTIVE'))
  print(create_access_token(str(u.id),{'version':u.token_version}))
 c.rollback()
`], { cwd: fileURLToPath(new URL('../../backend/', import.meta.url)), encoding: 'utf8' }).trim()
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
const pending = new Map(), calls = [], errors = []
let sequence = 0
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw Error(r.exceptionDetails.text); return r.result.value }
async function until(expression) { for (let i = 0; i < 150; i++) { if (await evaluate(expression)) return; await new Promise(r => setTimeout(r, 100)) } throw Error(`${expression}: ${errors}; ${await evaluate('document.body?.innerText')}`) }
async function click(text) { await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()===${JSON.stringify(text)}).click()`) }
const latest = () => calls.at(-1).body
ws.onmessage = async event => {
  const message = JSON.parse(event.data), item = pending.get(message.id)
  if (item) { clearTimeout(item.timer); pending.delete(message.id); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result) }
  if (message.method !== 'Fetch.requestPaused') return
  const { requestId, request } = message.params
  try {
    assert.equal(request.method, 'GET', 'No working mutations permitted')
    const url = new URL(request.url); let status = 200, data
    if (url.pathname.endsWith('/admin/business/summary')) {
      const response = await fetch('http://127.0.0.1:8000' + url.pathname + url.search, { headers: { Authorization: 'Bearer ' + token } })
      status = response.status; data = await response.json(); assert.equal(status, 200)
      calls.push({ path: url.pathname + url.search, status, body: { date_from: data.date_from, date_to: data.date_to, mode: data.mode, collections: data.collections } })
    } else if (url.pathname.endsWith('/auth/session')) data = { user: { id: 5, first_name: 'Read-only', last_name: 'Admin', email: 'probe@example.test' }, roles: ['ADMIN'] }
    else if (url.pathname.endsWith('/notifications/inbox')) data = { items: [], total: 0, unread_count: 0 }
    else if (url.pathname.endsWith('/notifications/me')) data = []
    else if (url.pathname.endsWith('/cart/summary')) data = { count: 0, total: '0.00', currency: 'INR' }
    else throw Error('Unexpected GET ' + url.pathname)
    await command('Fetch.fulfillRequest', { requestId, responseCode: status, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(data)).toString('base64') })
  } catch (error) { errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
}
try {
  await command('Page.enable'); await command('Runtime.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fitigo:access_token','readonly-dashboard-probe')` })
  await command('Page.navigate', { url: 'http://localhost:5173/admin?mode=test' })
  await until(`document.body?.innerText.includes('Verified collections — partial subtotal')`)
  const initial = latest()
  assert.equal(initial.collections.total, null)
  await click('Custom')
  for (const [label, value] of [['Start date', '2026-01-01'], ['End date', '2026-12-31']]) {
    await evaluate(`(()=>{const e=document.querySelector('input[aria-label="${label}"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'${value}');e.dispatchEvent(new Event('input',{bubbles:true}))})()`)
  }
  await click('Apply range')
  await until(`document.body?.innerText.includes('Individual bookings — verified partial')`)
  const full = latest(); assert.equal(full.date_from, '2026-01-01'); assert.equal(full.date_to, '2026-12-31')
  assert.equal(full.collections.known_dated_total, '300.00'); assert.equal(full.collections.total, null)
  assert.deepEqual(full.collections.excluded_by_category, { individual: 11, single_gym: 1, multi_gym: 2 })
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('.ad-metric')).find(c=>c.textContent.startsWith('Individual bookings — verified partial')).querySelector('strong').textContent.includes('300.00')`), true)
  for (const title of ['Revenue collected', 'Total customer collections']) {
    assert.equal(await evaluate(`Array.from(document.querySelectorAll('.ad-metric')).find(c=>c.textContent.startsWith('${title}')).querySelector('strong').textContent`), 'Not available yet')
    assert.equal(await evaluate(`Array.from(document.querySelectorAll('.ad-metric')).find(c=>c.textContent.startsWith('${title}')).querySelector('small').textContent.includes('300.00')`), true)
  }
  assert.equal(full.collections.gym_gross_share, null); assert.equal(full.collections.fitigo_commission, null)
  assert.equal(await evaluate(`document.body.innerText.includes('Commission settings alone do not establish historical earnings.')`), true)
  for (const [gymId, subtotal] of [['189', '300.00'], ['188', '0.00'], ['', '300.00']]) {
    const before = calls.length
    await evaluate(`(()=>{const s=Array.from(document.querySelectorAll('label')).find(l=>l.textContent.startsWith('Gym')).querySelector('select');s.value='${gymId}';s.dispatchEvent(new Event('change',{bubbles:true}))})()`)
    for (let i = 0; i < 150 && calls.length === before; i++) await new Promise(r => setTimeout(r, 100))
    assert.ok(calls.length > before)
    await until(`document.body?.innerText.includes('Verified collections — partial subtotal')`)
    const response = latest()
    assert.equal(response.collections.known_dated_total, subtotal)
    assert.equal(response.date_from, '2026-01-01')
    assert.equal(new URL('http://localhost' + calls.at(-1).path).searchParams.get('gym_id'), gymId || null)
  }
  await click('Today'); await until(`document.body?.innerText.includes('Verified collections — partial subtotal') && !document.body.innerText.includes('Individual bookings — verified partial')`)
  assert.equal(latest().collections.known_dated_total, '0.00')
  await evaluate(`(()=>{const s=Array.from(document.querySelectorAll('label')).find(l=>l.textContent.startsWith('Payment records')).querySelector('select');s.value='live';s.dispatchEvent(new Event('change',{bubbles:true}))})()`)
  await until(`Array.from(document.querySelectorAll('.ad-metric')).find(c=>c.textContent.startsWith('Revenue collected'))?.querySelector('strong').textContent.includes('0.00')`)
  assert.equal(latest().mode, 'live'); assert.equal(latest().collections.complete, true)
  for (const width of [360, 768, 1440]) { await command('Emulation.setDeviceMetricsOverride', { width, height: 1100, deviceScaleFactor: 1, mobile: width < 640 }); assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true) }
  assert.deepEqual(errors, [])
  writeFileSync(new URL(process.env.FITIGO_BROWSER_ARTIFACT || '../../DASHBOARD_RELEASE_BROWSER.json', import.meta.url), JSON.stringify({ read_only: true, calls }, null, 2), { flag: 'wx' })
  console.log('PASS actual read-only API + rendered dashboard: Today/full-2026/live, partial INR 300, complete totals unavailable, sharing evidence reasons, responsive layouts.')
} finally { ws.close(); await target.dispose() }