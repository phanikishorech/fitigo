import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const source = read('../src/owner/analyticsService.ts').replace(/import .* from '..\/services\/client'/, 'const request=(...args)=>globalThis.__analyticsRequest(...args)')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { analyticsService } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

test('analytics uses matching scope and server pagination without client totals', async () => {
  const calls = []; globalThis.__analyticsRequest = async (...args) => { calls.push(args); return {} }
  const scope = { date_from: '2026-10-01', date_to: '2026-10-27', gym_id: 7 }
  await analyticsService.overview(scope)
  await analyticsService.bookings(scope, 2, 'attended')
  await analyticsService.transactions(scope, 1, 'single_gym_membership', 'REFUNDED')
  await analyticsService.attendance(scope, 0)
  for (const [url, options] of calls) { assert.match(url, /gym_id=7/); assert.match(url, /date_from=2026-10-01&date_to=2026-10-27/); assert.equal(options.cache, 'no-store') }
  assert.match(calls[1][0], /category=attended&limit=10&offset=20/)
  assert.match(calls[2][0], /payment_status=REFUNDED&limit=10&offset=10/)
  await analyticsService.overview({ date_from: scope.date_from, date_to: scope.date_to })
  assert.doesNotMatch(calls[4][0], /gym_id=/)
})
test('existing analytics route is reused and SVG charts expose exact data accessibly', () => {
  const app = read('../src/owner/OwnerApp.tsx'), chart = read('../src/owner/ReportChart.tsx')
  assert.match(app, /route.page === 'analytics'/)
  assert.match(chart, /<polyline/); assert.match(chart, /aria-label/); assert.match(chart, /onFocus/)
  assert.match(chart, /onClick/); assert.match(chart, /View chart data/); assert.match(chart, /No estimated values/)
  const page = read('../src/owner/Analytics.tsx')
  for (const label of ['Visits Over Time', 'Revenue Over Time', 'Booking outcomes', 'Payment records', 'Successful attendance', 'All Gyms']) assert.ok(page.includes(label))
})

test('revenue labels use server mode, not a new frontend flag or live-only label', () => {
  const metrics = read('../src/owner/ReportMetrics.tsx')
  assert.match(metrics, /data.revenue.mode/)
  assert.match(metrics, /No real money/)
  assert.doesNotMatch(metrics, /Verified live paid|localStorage|VITE_/)
  assert.match(read('../src/owner/Analytics.tsx'), /summary.revenue.mode/)
})