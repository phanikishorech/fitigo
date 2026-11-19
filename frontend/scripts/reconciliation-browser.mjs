// Isolated browser storage; all API calls are mocked, including review writes.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, writes = 0
const pending = new Map(), errors = []
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text); return result.result.value }
async function until(expression) { for (let n = 0; n < 100; n++) { if (await evaluate(expression)) return; await new Promise(resolve => setTimeout(resolve, 100)) } throw Error(`${expression}: ${await evaluate('document.body?.innerText')}; ${errors}`) }
function fixture(url, method) {
  if (method !== 'GET') { writes++; throw Error('Unexpected mutation in read-only browser test') }
  if (url.pathname.endsWith('/auth/session')) return { user: { id: 5, first_name: 'Review', last_name: 'Admin', email: 'admin@example.test' }, roles: ['ADMIN'] }
  if (url.pathname.endsWith('/notifications/inbox')) return { items: [], total: 0, unread_count: 0 }
  if (url.pathname.endsWith('/notifications/me')) return []
  if (url.pathname.endsWith('/cart/summary')) return { count: 0, total: '0.00', currency: 'INR' }
  if (url.pathname.includes('/records/')) return { id: 'source-fixture', kind: 'source', snapshot: { transaction_basis: { tax_amount: null } }, snapshot_hash: 'a'.repeat(64), integrity_valid: true }
  if (url.pathname.endsWith('/reviews')) return { items: [], total: 0 }
  if (url.pathname.endsWith('/financial-reconciliation')) return {
    available: true, mode: url.searchParams.get('mode'), view: url.searchParams.get('view'), read_only: true,
    totals_scope: 'CURRENT_PAGE_ONLY', notice: 'Unknown is not zero. No GET creates financial records.',
    page_totals: { net_payable: null, gross_entitlement: '85.00' },
    items: [{ id: 'source-fixture', status: 'UNKNOWN', trace: { source_evidence_id: 'source-fixture' }, tax: { tax_amount: null, status: 'UNKNOWN' } }], total: 1,
    controls: { gates: { source_evidence_enabled: false, marketplace_allocations_enabled: false, marketplace_live_allocations_enabled: false, marketplace_payouts_enabled: false }, missing_tables: [], schema_ready: true, activation_authorized: false, can_activate_from_ui: false, notice: 'No endpoint changes gates or sends money.', checks: ['Explicit deployment approval required'] }
  }
  throw Error(`Unexpected API ${url.pathname}`)
}
ws.onmessage = async event => {
  const message = JSON.parse(event.data), item = pending.get(message.id)
  if (item) { clearTimeout(item.timer); pending.delete(message.id); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result) }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
  if (message.method !== 'Fetch.requestPaused') return
  const { requestId, request } = message.params
  try {
    const data = fixture(new URL(request.url), request.method)
    await command('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(data)).toString('base64') })
  } catch (error) { errors.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
}
try {
  await command('Runtime.enable'); await command('Page.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('fitigo:access_token','isolated-reconciliation-fixture')` })
  await command('Page.navigate', { url: (process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173') + '/admin/financial-reconciliation' })
  await until(`document.body.innerText.includes('Unknown / unresolved')`)
  assert.equal(await evaluate(`document.body.innerText.includes('Activation authorized: No')`), true)
  await evaluate(`document.querySelector('.ag-version summary').click()`)
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('Inspect source')).click()`)
  await until(`document.body.innerText.includes('Snapshot integrity verified')`)
  await evaluate(`document.querySelector('dialog button[aria-label="Close dialog"]').click()`)
  for (const width of [360, 768, 1440]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 1100, deviceScaleFactor: 1, mobile: width < 640 })
    assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), true, `width ${width}`)
  }
  for (const label of ['Individual', 'Single-Gym', 'Authorized no-show', 'Multi-Gym months', 'Gateway fees', 'Unallocated collections', 'Payout balances', 'Corrections / differences']) {
    await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent===${JSON.stringify(label)}).click()`)
    await until(`document.body.innerText.includes('Current page totals only')`)
  }
  await until(`document.body.innerText.includes('Controlled correction reviews')`)
  assert.equal(writes, 0); assert.deepEqual(errors, [])
  console.log('PASS reconciliation views, unknown amounts, disabled activation, source drill-down and 360/768/1440 layouts. All API calls mocked; zero mutations.')
} finally { ws.close(); await target.dispose() }