// Isolated browser/API fixtures. No real agreement or customer writes.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
// Pure schema generation only; no database session import or provider calls.
const policyCatalog = JSON.parse(execFileSync(fileURLToPath(new URL('../../backend/.venv/Scripts/python.exe', import.meta.url)), ['-B', '-c', 'import json; from app.services.accounting_policy import contract_catalog; print(json.dumps(contract_catalog()))'], { cwd: fileURLToPath(new URL('../../backend/', import.meta.url)), encoding: 'utf8' }))
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, saved = [], configured = true, lastScope = null
const pending = new Map(), errors = []
const proposal = { attended: { gym_percent: '85.00', fitigo_percent: '15.00' }, no_show: { gym_percent: '70.00', fitigo_percent: '30.00' }, single_gym: { gym_percent: '85.00', fitigo_percent: '15.00' }, multi_gym: { payout_per_visit: null, visits_per_member_month: null, payout_cap_per_member_month: null }, settlements: { booking_cycle: 'WEEKLY', multi_gym_cycle: 'MONTHLY', monthly_single_cycle: 'NEXT_CYCLE', quarterly_single_cycle: 'UPFRONT', half_yearly_single_cycle: 'UPFRONT', yearly_single_cycle: 'UPFRONT', minimum_payout: '500.00', admin_approval_required: true }, sharing_basis: 'AFTER_DISCOUNTS_EXCLUDING_TAX', gateway_fees: 'SEPARATE_ACTUAL', wallet_same_agreement: true, group_basis: 'ATTENDED_VISITORS_WHEN_UNIT_PRICED', business_model: 'AGENT_MARKETPLACE', membership_recognition: 'NOT_APPROVED' }
function fixture(url, method, body, headers) {
  const path = url.pathname
  if (path.endsWith('/auth/session')) return { user: { id: 1, first_name: 'Agreement', last_name: 'Admin', email: 'admin@example.test' }, roles: ['ADMIN'] }
  if (path.endsWith('/notifications/inbox')) return { items: [], total: 0, unread_count: 0 }
  if (path.endsWith('/notifications/me')) return []
  if (path.endsWith('/cart/summary')) return { count: 0, total: '0.00', currency: 'INR' }
  if (path.endsWith('/admin/settings')) return { payment: { enabled: true, provider: 'RAZORPAY', mode: 'test', wallet_test_credit: false }, limitations: {} }
  if (path.endsWith('/financial-agreements/policy-validation')) {
    assert.equal(body.policy_contract.contract_version, 2)
    assert.equal(body.policy_contract.attended.rounding, 'HALF_UP')
    return { status: 'NOT_CONFIGURED', contract_version: 2, posting_eligible: false, reason: 'Policy only; no posting.', sections: { attended: { status: 'AWAITING_APPROVAL', missing_fields: ['allocation_basis'], posting_eligible: false, reason: 'Missing fields' } } }
  }
  if (path.endsWith('/financial-agreements')) {
    if (method === 'POST') {
      assert.equal(body.expected_version, 0); assert.equal(body.mode, 'test'); assert.equal(body.gym_id, null)
      assert.equal(body.terms.attended.gym_percent, '80'); assert.equal(body.terms.attended.fitigo_percent, '20')
      assert.equal(body.acknowledge_configuration_only, true)
      assert.equal(body.terms.policy_contract.contract_version, 2)
      assert.equal(body.terms.policy_contract.attended.rounding, 'HALF_UP')
      assert.ok(Object.entries(headers).some(([key, value]) => key.toLowerCase() === 'idempotency-key' && value.length >= 8))
      const row = { id: 1, scope_id: 1, version: 1, ...body, created_at: '2026-11-13T12:00:00+05:30', actor_id: 1, applies_until: null, superseded_at: null, state: 'SCHEDULED', statutory_reporting_enabled: false }
      saved.push(row); return row
    }
    lastScope = Object.fromEntries(url.searchParams)
    const history = !url.searchParams.has('gym_id') && url.searchParams.get('mode') === 'test' ? saved : []
    return { policy_catalog: policyCatalog, available: configured, mode: url.searchParams.get('mode'), gym_id: url.searchParams.has('gym_id') ? Number(url.searchParams.get('gym_id')) : null, server_time: '2026-11-13T12:00:00+05:30', statutory_reporting_enabled: false, posting_enabled: false, options: [{ id: 7, name: 'Override gym' }], notice: 'Configuration only. No commissions or payouts.', reason: configured ? null : 'Apply migration d46e70ba9268 before configuring revenue sharing.', latest_version: history.length, latest: history.at(-1) || null, effective: null, template: configured ? proposal : null, history, total: history.length, limits_notice: 'Blank limits mean not configured.' }
  }
  throw Error(`Unexpected API ${method} ${path}`)
}
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value }
async function until(expression) { for (let n = 0; n < 150; n++) { if (await evaluate(expression)) return; await new Promise(r => setTimeout(r, 100)) } throw Error(`${expression}: ${await evaluate('document.body?.innerText')}; ${errors}`) }
async function click(label) { await until(`Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()===${JSON.stringify(label)} && !b.disabled)`); await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()===${JSON.stringify(label)}).click()`) }
async function input(label, value) { await evaluate(`(()=>{const label=Array.from(document.querySelectorAll('.ag-form label')).find(l=>l.textContent.trim().startsWith(${JSON.stringify(label)}));const el=label.querySelector('input,textarea');Object.getOwnPropertyDescriptor(el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('input',{bubbles:true}))})()`) }
ws.onmessage = async event => {
  const m = JSON.parse(event.data), item = pending.get(m.id)
  if (item) { clearTimeout(item.timer); pending.delete(m.id); m.error ? item.reject(Error(m.error.message)) : item.resolve(m.result) }
  if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.text)
  if (m.method !== 'Fetch.requestPaused') return
  const { requestId, request } = m.params
  try {
    const data = fixture(new URL(request.url), request.method, request.postData ? JSON.parse(request.postData) : {}, request.headers)
    await command('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(data)).toString('base64') })
  } catch (error) { errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
}
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fitigo:access_token','isolated-agreement-fixture')` })
  await command('Page.navigate', { url: origin + '/admin/settings' })
  await until(`document.querySelector('.ag-proposal summary') !== null`)
  await evaluate(`document.querySelector('.ag-proposal summary').click()`)
  assert.equal(await evaluate(`document.querySelector('[aria-label="Attended individual bookings gym percent"]').value`), '85.00')
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Review new agreement version').disabled`), true)
  await input('Gym share (%)', '80')
  await until(`document.body.innerText.includes('Shares must total exactly 100%')`)
  await input('FitiGo share (%)', '20')
  await evaluate(`Array.from(document.querySelectorAll('.ag-form label')).find(l=>l.textContent.includes('Include policy contract version 2')).querySelector('input').click()`)
  await until(`document.querySelector('[aria-label="attended.rounding"]') !== null`)
  assert.equal(await evaluate(`document.querySelector('[aria-label="attended.rounding"]').value`), '')
  await evaluate(`(()=>{const field=document.querySelector('[aria-label="attended.rounding"]');for(let parent=field.parentElement;parent;parent=parent.parentElement){if(parent.tagName==='DETAILS')parent.open=true}field.value='HALF_UP';field.dispatchEvent(new Event('change',{bubbles:true}))})()`)
  await click('Validate policy readiness')
  await until(`document.body.innerText.includes('Awaiting approval')`)
  assert.equal(saved.length, 0)
  await input('Effective from (IST)', '2099-01-01T10:00:00')
  await input('Agreement reference', 'Contract-2026-fixture')
  await input('Reason for this change', 'Adjusted commission agreement')
  await evaluate(`Array.from(document.querySelectorAll('.ag-form label')).find(l=>l.textContent.includes('I understand')).querySelector('input').click()`)
  for (const width of [360, 768, 1440]) { await command('Emulation.setDeviceMetricsOverride', { width, height: 1100, deviceScaleFactor: 1, mobile: width < 640 }); assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true, `width ${width}`) }
  await click('Review new agreement version')
  await until(`document.querySelector('dialog[open]') !== null`)
  assert.equal(saved.length, 0)
  await click('Save future version')
  await until(`document.body.innerText.includes('New agreement version saved')`)
  assert.equal(saved.length, 1)
  assert.ok(await evaluate(`document.body.innerText.includes('Version 1')`))
  await evaluate(`(()=>{const el=Array.from(document.querySelectorAll('label')).find(l=>l.textContent.includes('Agreement scope')).querySelector('select');el.value='7';el.dispatchEvent(new Event('change',{bubbles:true}))})()`)
  await until(`document.querySelector('.ag-proposal summary') !== null && !document.body.innerText.includes('New agreement version saved')`)
  await evaluate(`document.querySelector('.ag-proposal summary').click()`)
  await until(`document.body.innerText.includes('Return this gym to the standard agreement')`)
  assert.equal(lastScope.gym_id, '7')
  configured = false; await click('Reload agreement history')
  await until(`document.body.innerText.includes('Apply migration d46e70ba9268')`)
  assert.equal(await evaluate(`document.querySelector('.ag-form') === null`), true)
  assert.deepEqual(errors, [])
  console.log('PASS agreement proposal/edit/share validation/review/save/history/gym scope/migration guard; 360/768/1440 layouts. All writes mocked.')
} finally { ws.close(); await target.dispose() }