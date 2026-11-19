import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
async function load(path, transform = source => source) {
  const code = ts.transpileModule(transform(read(path)), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
}
test('exactly seven business modules in the primary navigation', () => {
  const source = read('../src/admin/AdminLayout.tsx').split('export function Logo')[0]
  const labels = [...source.matchAll(/label: '([^']+)'/g)].map(match => match[1])
  assert.deepEqual(labels, ['Dashboard', 'Gyms', 'Users', 'Bookings', 'Memberships', 'Reports', 'Commission Settings'])
})
test('all business routes and default landing remain available; diagnostics unmounted', async () => {
  const { adminRoute } = await load('../src/admin/routes.ts')
  for (const [path, page] of [['/admin','dashboard'], ['/admin/gyms','gyms'], ['/admin/users','users'], ['/admin/bookings','bookings'], ['/admin/memberships','memberships'], ['/admin/reports','reports'], ['/admin/commission-settings','financial-settings']]) assert.equal(adminRoute(path).page, page)
  for (const path of ['financial-reconciliation', 'readiness', 'settings', 'audit-logs', 'support']) assert.equal(adminRoute('/admin/' + path).page, 'notFound')
  assert.doesNotMatch(read('../src/admin/AdminApp.tsx'), /import\('\.\/(FinancialOverview|FinancialReconciliation|MarketplaceFinancials|Readiness|WorkflowSettings)'\)/)
})
test('last seven days is inclusive rolling window; shared week behavior retained', async () => {
  const { presetRange } = await load('../src/utils/dateRange.ts')
  assert.deepEqual(presetRange('last7', '2026-11-17'), { date_from: '2026-11-11', date_to: '2026-11-17' })
  assert.deepEqual(presetRange('week', '2026-11-17'), { date_from: '2026-11-16', date_to: '2026-11-17' })
  assert.deepEqual(presetRange('yesterday', '2026-11-17'), { date_from: '2026-11-16', date_to: '2026-11-16' })
})
test('business queries use existing client and never request payout mutations', async () => {
  const { businessService } = await load('../src/admin/businessService.ts', source => source.replace(/import \{ request \}[^\n]+/, 'const request=(...args)=>globalThis.businessRequest(...args)').replace(/import \{ financialQuery[^\n]+/, 'const financialQuery=o=>new URLSearchParams(Object.entries(o).filter(([,v])=>v!==undefined)).toString()'))
  let args; globalThis.businessRequest = async (...value) => { args = value }
  await businessService.summary({ date_from: '2026-11-01', date_to: '2026-11-17', mode: 'test' })
  assert.equal(args[0], '/admin/business/summary?date_from=2026-11-01&date_to=2026-11-17&mode=test'); assert.equal(args[1].cache, 'no-store')
  await businessService.memberships({ status: 'PAUSED', user_id: 7, limit: 20, offset: 20 })
  assert.match(args[0], /status=PAUSED&user_id=7/)
  assert.doesNotMatch(read('../src/admin/BusinessOverview.tsx'), /marketplaceService\.create|transition|SettlementSettings|source_evidence_enabled/)
})
test('commission editor retains server-owned settings, dates, retry and history without diagnostics', () => {
  const source = read('../src/admin/FinancialSettings.tsx')
  for (const text of ['structuredClone(config.template', 'structuredClone(settings)', 'expected_version', 'expected_effective_version_id', 'crypto.randomUUID', 'row.actor_id', 'row.reason', 'row.effective_from', 'gateway_fee', 'reference_visits']) assert.ok(source.includes(text), text)
  assert.doesNotMatch(source, /processing_blockers|<SettlementSettingsEditor|JSON.stringify\(row.terms|schema is not deployed/)
  assert.match(source, /Commission Settings/)
})
test('reports offer exactly seven nonduplicated business views and truthful unknown exports', () => {
  const source = read('../src/admin/BusinessOverview.tsx')
  assert.equal((source.match(/label: '(?:Visit|Revenue|Gym performance|Membership|Booking and cancellation|Customer|Wallet) report'/g) || []).length, 7)
  assert.match(source, /data.collections.complete \? r\[/)
  assert.match(source, /Not available/)
  assert.match(source, /analyticsCsv/)
})
test('partial collection evidence never masquerades as a complete total or commission', () => {
  const source = read('../src/admin/BusinessOverview.tsx')
  for (const text of ['known_dated_categories', 'known_dated_total', 'exclusion_reasons', 'Verified collections — partial subtotal', 'not the complete total', 'data.wallet.reason', 'unclassified_mode_balance']) assert.ok(source.includes(text), text)
  assert.match(source, /title="Revenue collected" value=\{data.collections.total\}/)
})
test('all seven report projections preserve columns, unknowns, empty sets and a large gym list', async () => {
  const { reportRows } = await load('../src/admin/BusinessOverview.tsx', source =>
    source.slice(source.indexOf('export function reportRows'), source.indexOf('function Report('))
      .replace('export function reportRows', "const categories=[{key:'individual',label:'Individual bookings'},{key:'single_gym',label:'Single-Gym memberships'},{key:'multi_gym',label:'Multi-Gym memberships'}]; export function reportRows"))
  const category = { sales_count: 1, sales_value: '500.00', active: 1, expired: 0 }
  const data = { series: [{ date: '2026-11-12', individual: 1, single_gym: 2, multi_gym: 3, individual_collections: '150.00', single_gym_collections: '500.00', multi_gym_collections: '1000.00' }],
    collections: { complete: true }, memberships: { categories: { SINGLE_GYM: category, MULTI_GYM: category } },
    bookings: { total: 8, cancelled: 3, cancellation_rate: 37.5, no_show: 0, no_show_rate: 0 },
    wallet: { outstanding: '200.00', credits: '300.00', spending: '100.00', cancellation_credits: '300.00' },
    customers: { most_active: [{ user_id: 7, visits: 6 }] }, gyms: [] }
  for (const section of ['visits','revenue','gyms','memberships','bookings','customers','wallet']) {
    const table = reportRows(section, data)
    assert.ok(table.headers.length > 0)
    for (const row of table.rows) assert.equal(row.length, table.headers.length)
  }
  assert.deepEqual(reportRows('revenue', data).rows[0], ['2026-11-12','150.00','500.00','1000.00'])
  data.collections.complete = false
  assert.deepEqual(reportRows('revenue', data).rows[0], ['2026-11-12',null,null,null])
  data.series = []; data.customers.most_active = []
  for (const section of ['visits','revenue','gyms','customers']) assert.deepEqual(reportRows(section, data).rows, [])
  data.gyms = Array.from({ length: 5000 }, (_, id) => ({ name: `Gym ${id}`, status: 'APPROVED', visits: id, attended_value: '100.00', single_membership_sales_value: '500.00' }))
  assert.equal(reportRows('gyms', data).rows.length, 5000)
  assert.equal(reportRows('gyms', data).rows.at(-1)[0], 'Gym 4999')
})