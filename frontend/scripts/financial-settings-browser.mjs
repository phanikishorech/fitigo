// Browser fixture only: every API request is intercepted; no application writes.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const defaults = JSON.parse(execFileSync(fileURLToPath(new URL('../../backend/.venv/Scripts/python.exe', import.meta.url)), ['-B', '-c', 'import json; from app.schemas.gym_financial_settings import GymFinancialSettings; print(GymFinancialSettings().model_dump_json())'], { cwd: fileURLToPath(new URL('../../backend/', import.meta.url)), encoding: 'utf8' }))
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, available = true, saved = [], keys = [], lastScope
const pending = new Map(), errors = []
function fixture(url, method, body, headers) {
  const path = url.pathname
  if (path.endsWith('/auth/session')) return { user: { id: 5, first_name: 'Financial', last_name: 'Admin', email: 'admin@example.test' }, roles: ['ADMIN'] }
  if (path.endsWith('/notifications/inbox')) return { items: [], total: 0, unread_count: 0 }
  if (path.endsWith('/notifications/me')) return []
  if (path.endsWith('/cart/summary')) return { count: 0, total: '0.00', currency: 'INR' }
  if (path.endsWith('/financial-settings/gyms')) {
    const all = [{ id: 7, name: 'Alpha gym' }, { id: 8, name: 'Beta gym' }, ...Array.from({ length: 43 }, (_, i) => ({ id: 100 + i, name: `Gym ${i}` }))]
    const items = all.filter(gym => gym.name.toLowerCase().includes((url.searchParams.get('q') || '').toLowerCase()))
    const offset = Number(url.searchParams.get('offset')), limit = Number(url.searchParams.get('limit'))
    assert.ok(offset >= 0, 'Selector must never request a negative offset')
    return { items: items.slice(offset, offset + limit), total: items.length }
  }
  if (path.endsWith('/financial-settings')) {
    if (method === 'POST') {
      assert.equal(body.gym_id, 7); assert.equal(body.mode, 'test'); assert.equal(body.expected_version, 0)
      assert.equal(body.expected_effective_version_id, null)
      assert.deepEqual(body.settings.individual.revenue, { gym_percent: '80', fitigo_percent: '20' })
      assert.equal(body.settings.multi_gym.reference_amount, '3000.00')
      assert.equal(body.settings.multi_gym.reference_visits, 100)
      assert.equal(body.settings.multi_gym.rounding, null)
      assert.equal(body.acknowledge_configuration_only, true)
      const key = Object.entries(headers).find(([name]) => name.toLowerCase() === 'idempotency-key')?.[1]
      assert.ok(key); keys.push(key)
      if (keys.length === 1) return { simulatedFailure: true }
      assert.equal(keys[1], keys[0])
      const row = { id: 1, version: 1, state: 'SCHEDULED', effective_from: body.effective_from, applies_until: null, actor_id: 5, created_at: '2026-11-12T12:00:00Z', reason: body.reason, terms: { financial_settings: body.settings } }
      saved.push(row); return row
    }
    lastScope = Object.fromEntries(url.searchParams)
    assert.ok(Number(lastScope.offset) >= 0, 'History must never request a negative offset')
    const gymId = Number(url.searchParams.get('gym_id')), mode = url.searchParams.get('mode')
    const history = gymId === 7 && mode === 'test' ? saved : []
    return { gym_id: gymId, gym_name: gymId === 7 ? 'Alpha gym' : 'Beta gym', mode, available, reason: 'Financial settings require migration d46e70ba9268.',
      posting_enabled: false, processing_blockers: ['CALCULATION_ADAPTER_NOT_CONNECTED'], template: available ? history.at(-1)?.terms.financial_settings || defaults : null,
      latest_version: history.length, latest: history.at(-1) || null, effective: null, legacy_replacement_required: false, history, total: history.length }
  }
  throw Error(`Unexpected API ${method} ${path}`)
}
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text); return result.result.value }
async function until(expression) { for (let n = 0; n < 150; n++) { if (await evaluate(expression)) return; await new Promise(resolve => setTimeout(resolve, 100)) } throw Error(`${expression}: ${await evaluate('document.body?.innerText')}; ${errors}`) }
async function click(label) { await until(`Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()===${JSON.stringify(label)} && !b.disabled)`); await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()===${JSON.stringify(label)}).click()`) }
async function input(label, value) { await evaluate(`(()=>{const label=Array.from(document.querySelectorAll('label')).find(l=>l.textContent.trim().startsWith(${JSON.stringify(label)}));const el=label.querySelector('input,textarea');Object.getOwnPropertyDescriptor(el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('input',{bubbles:true}))})()`) }
async function select(label, value) { await evaluate(`(()=>{const el=Array.from(document.querySelectorAll('label')).find(l=>l.textContent.includes(${JSON.stringify(label)})).querySelector('select');el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change',{bubbles:true}))})()`) }
ws.onmessage = async event => {
  const message = JSON.parse(event.data), item = pending.get(message.id)
  if (item) { clearTimeout(item.timer); pending.delete(message.id); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result) }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
  if (message.method !== 'Fetch.requestPaused') return
  const { requestId, request } = message.params
  try {
    const data = fixture(new URL(request.url), request.method, request.postData ? JSON.parse(request.postData) : {}, request.headers)
    await command('Fetch.fulfillRequest', { requestId, responseCode: data.simulatedFailure ? 503 : 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(data.simulatedFailure ? { detail: 'Simulated interrupted request. Retry unchanged.' } : data)).toString('base64') })
  } catch (error) { errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
}
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fitigo:access_token','isolated-financial-settings-fixture')` })
  await command('Page.navigate', { url: origin + '/admin/commission-settings' })
  await until(`document.body?.innerText.includes('Select a gym to view its settings')`)
  await until(`Array.from(document.querySelectorAll('label')).some(l=>l.textContent.includes('Select gym') && l.querySelector('select option[value="7"]'))`)
  assert.equal(await evaluate(`document.querySelector('[aria-label="Previous page"]').disabled`), true, 'First selector page cannot go backwards')
  await evaluate(`document.querySelector('[aria-label="Next page"]').click()`)
  await until(`document.querySelector('option[value="118"]') !== null`)
  assert.equal(await evaluate(`document.querySelector('[aria-label="Previous page"]').disabled`), false, 'Second selector page must return to first')
  await evaluate(`document.querySelector('[aria-label="Next page"]').click()`)
  await until(`document.querySelector('option[value="142"]') !== null`)
  assert.equal(await evaluate(`document.querySelector('[aria-label="Next page"]').disabled`), true)
  await evaluate(`document.querySelector('[aria-label="Previous page"]').click()`)
  await until(`document.querySelector('option[value="118"]') !== null`)
  await evaluate(`document.querySelector('[aria-label="Previous page"]').click()`)
  await until(`document.querySelector('option[value="7"]') !== null`)
  await select('Select gym', '7')
  await until(`document.querySelector('.ag-proposal summary') !== null`)
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('[aria-label="Previous page"]')).at(-1).disabled`), true, 'First history page cannot go backwards')
  await evaluate(`document.querySelector('.ag-proposal summary').click()`)
  assert.equal(await evaluate(`document.querySelector('.ag-form input[type=number]').value`), '85')
  await input('Gym owner %', '80')
  await until(`document.body.innerText.includes('Percentages must total exactly 100.')`)
  await input('FitiGo %', '20'); await input('Effective from', '2099-01-01T10:00'); await input('Change reason', 'Independent gym contract fixture')
  await evaluate(`document.querySelector('.ag-check input').click()`)
  for (const width of [360, 768, 1440]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 1100, deviceScaleFactor: 1, mobile: width < 640 })
    assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true, `width ${width}`)
  }
  await click('Review future settings'); await until(`document.querySelector('dialog[open]') !== null`)
  assert.equal(saved.length, 0)
  await click('Save future version'); await until(`document.body.innerText.includes('Retry uses the same unchanged request')`)
  await click('Save future version'); await until(`document.body.innerText.includes('Future version saved.')`)
  assert.equal(saved.length, 1); assert.equal(keys.length, 2)
  await click('Reload settings and history')
  await until(`document.body.textContent.includes('Version 1') && document.body.textContent.includes('Independent gym contract fixture')`)
  await command('Page.reload')
  await until(`document.querySelector('option[value="7"]') !== null`)
  await select('Select gym', '7')
  await until(`document.body.textContent.includes('Version 1') && document.body.textContent.includes('Independent gym contract fixture')`)
  await select('Select gym', '8'); await until(`document.body.innerText.includes('No gym-specific versions')`)
  assert.equal(lastScope.gym_id, '8')
  await select('Payment environment', 'live'); await until(`document.querySelector('.ag-proposal summary') !== null && document.body.innerText.includes('No gym-specific versions')`)
  assert.equal(lastScope.mode, 'live')
  available = false; await click('Reload settings and history')
  await until(`document.body.innerText.includes('Commission settings are temporarily unavailable')`)
  assert.equal(await evaluate(`document.querySelector('.ag-form') === null`), true)
  assert.deepEqual(errors, [])
  console.log('PASS Financial Settings defaults/edit/review/retry/history/gym and environment isolation/missing-schema guard; 360/768/1440 layouts. All API writes mocked.')
} finally { ws.close(); await target.dispose() }