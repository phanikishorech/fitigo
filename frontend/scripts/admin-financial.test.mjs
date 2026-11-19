import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const source = read('../src/admin/financialService.ts').replace(/import \{ request \}[^\n]+/, 'const request=(...args)=>globalThis.financialRequest(...args)')
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { financialService } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
test('all three admin views request the identical financial filter contract', async () => {
  const calls = []; globalThis.financialRequest = async (...args) => { calls.push(args); return {} }
  const filters = { date_from: '2026-11-01', date_to: '2026-11-13', gym_id: 3, mode: 'live', source: 'WALLET' }
  for (const view of ['dashboard', 'analytics', 'reports']) await financialService.report(view, filters)
  assert.deepEqual(calls.map(([url]) => url.split('?')[0]), ['/admin/dashboard/summary', '/admin/analytics', '/admin/reports/financial'])
  assert.equal(new Set(calls.map(([url]) => url.split('?')[1])).size, 1)
  for (const [url, options] of calls) { assert.match(url, /mode=live/); assert.match(url, /source=WALLET/); assert.match(url, /financial=true/); assert.equal(options.cache, 'no-store') }
})
test('wallet ledger preserves environment, date, direction, type and pagination', async () => {
  let captured; globalThis.financialRequest = async url => { captured = url; return {} }
  await financialService.ledger({ date_from: '2026-11-01', date_to: '2026-11-13', mode: 'test' }, 'IN', 'CANCELLATION_CREDIT', 2)
  const query = new URL(captured, 'https://example.test').searchParams
  assert.equal(query.get('offset'), '50'); assert.equal(query.get('limit'), '25'); assert.equal(query.get('mode'), 'test'); assert.equal(query.get('txn_type'), 'CANCELLATION_CREDIT')
})
test('financial UI never labels collected or cancelled payments as earned revenue', () => {
  const ui = read('../src/admin/FinancialOverview.tsx')
  for (const label of ['Not configured', 'Attended individual booking value', 'No-show gross forfeited amount', 'Outstanding customer wallet liability', 'capture date unavailable', 'first valid check-in date']) assert.ok(ui.includes(label), label)
  assert.doesNotMatch(ui, /revenue\.in_period|Paid bookings · scheduled|title="Booking revenue"/)
  assert.match(ui, /<polyline/); assert.match(ui, /<meter/); assert.match(ui, /View chart data/)
})
test('everyday dashboard and reports use the business presentation, not financial operations', () => {
  assert.match(read('../src/admin/Dashboard.tsx'), /BusinessOverview/)
  assert.match(read('../src/admin/AdminApp.tsx'), /BusinessOverview reportsOnly/)
  assert.doesNotMatch(read('../src/admin/AdminApp.tsx'), /FinancialReconciliation|MarketplaceFinancials/)
  const routes = read('../src/admin/routes.ts'); assert.match(routes, /reports/); assert.match(routes, /analytics/)
})