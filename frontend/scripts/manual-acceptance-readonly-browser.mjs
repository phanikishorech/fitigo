// Working-data GET probe. No application lifespan, login writes, provider calls or POSTs.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { writeFileSync } from 'node:fs'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const before = process.argv.includes('--before')
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
let sequence = 0
const pending = new Map(), calls = [], errors = []
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw Error(r.exceptionDetails.text); return r.result.value }
async function until(expression) { for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await new Promise(r => setTimeout(r, 100)) } console.error(errors, calls, await evaluate('document.body.innerText')); throw Error(expression) }
ws.onmessage = async event => {
  const message = JSON.parse(event.data), item = pending.get(message.id)
  if (item) { clearTimeout(item.timer); pending.delete(message.id); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result) }
  if (message.method !== 'Fetch.requestPaused') return
  const { requestId, request } = message.params
  try {
    assert.equal(request.method, 'GET', 'Working-data browser forbids mutations')
    const url = new URL(request.url)
    let status = 200, data
    if (/\/admin\/(financial-settings|business\/summary)/.test(url.pathname)) {
      const response = await fetch('http://127.0.0.1:8000' + url.pathname + url.search, { headers: { Authorization: 'Bearer ' + token } })
      status = response.status; data = await response.json()
      calls.push({ path: url.pathname + url.search, status, body: data })
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
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fitigo:access_token','readonly-probe')` })
  await command('Page.navigate', { url: 'http://localhost:5173/admin/commission-settings' })
  await until(`document.querySelector('select option[value="188"]') !== null`)
  await evaluate(`(()=>{const s=Array.from(document.querySelectorAll('label')).find(l=>l.textContent.startsWith('Select gym')).querySelector('select');s.value='188';s.dispatchEvent(new Event('change',{bubbles:true}))})()`)
  await until(`document.body.innerText.includes('No gym-specific versions')`)
  if (before) {
    await evaluate(`Array.from(document.querySelectorAll('[aria-label="Previous page"]')).at(-1).click()`)
    for (let i = 0; i < 100 && !calls.some(c => c.status === 422); i++) await new Promise(r => setTimeout(r, 100))
    const failure = calls.find(c => c.status === 422)
    assert.ok(failure); console.log(JSON.stringify(failure, null, 2))
  } else {
    assert.equal(await evaluate(`Array.from(document.querySelectorAll('[aria-label="Previous page"]')).every(b=>b.disabled)`), true)
    await evaluate(`document.querySelector('[aria-label="Next page"]').click()`)
    await until(`document.querySelector('select option[value="190"]') !== null`)
    assert.equal(await evaluate(`document.querySelector('[aria-label="Previous page"]').disabled`), false)
    assert.ok(calls.filter(c => c.path.includes('/gyms?')).some(c => c.body.total === 39))
  }
  await command('Page.navigate', { url: 'http://localhost:5173/admin?gym_id=188' })
  await until(`document.body.innerText.includes('Wallet activity')`)
  await evaluate(`Array.from(document.querySelectorAll('summary')).find(s=>s.textContent==='Wallet activity').click()`)
  await until(`document.body.innerText.includes('Unused customer wallet balance')`)
  const scoped = calls.filter(c => c.path.includes('/business/summary')).at(-1)
  assert.equal(scoped.body.wallet.outstanding, null)
  await command('Page.navigate', { url: 'http://localhost:5173/admin' })
  await until(`document.body.innerText.includes('Wallet activity')`)
  await evaluate(`Array.from(document.querySelectorAll('summary')).find(s=>s.textContent==='Wallet activity').click()`)
  await until(`document.body.innerText.includes('Unused customer wallet balance')`)
  const all = calls.filter(c => c.path.includes('/business/summary')).at(-1)
  assert.equal(all.body.wallet.outstanding, '750.00')
  assert.deepEqual(errors, [])
  writeFileSync(new URL(`../../MANUAL_FIXES_BROWSER_${before ? 'BEFORE' : 'AFTER'}.json`, import.meta.url), JSON.stringify({ read_only: true, calls }, null, 2), { flag: 'wx' })
  console.log('PASS read-only working API browser probe; no mutations or payment calls.')
} finally { ws.close(); await target.dispose() }