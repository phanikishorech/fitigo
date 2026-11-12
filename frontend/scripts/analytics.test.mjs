import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

async function load(path, transform = source => source) {
  const code = ts.transpileModule(transform(readFileSync(new URL(path, import.meta.url), 'utf8')), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
}
const { comparison, analyticsCsv, csvCell } = await load('../src/utils/analytics.ts')
const { adminRoute } = await load('../src/admin/routes.ts')
const { analyticsQuery, analyticsService } = await load('../src/admin/analyticsService.ts', s => s.replace(/import \{ request \}[^\n]+/, 'const request=(...args)=>globalThis.analyticsRequest(...args)'))

test('analytics is a dedicated admin route', () => assert.equal(adminRoute('/admin/analytics').page, 'analytics'))
test('comparison never invents growth from a zero baseline', () => {
  assert.equal(comparison(0, 0), 'No change from previous period')
  assert.equal(comparison(5, 0), 'No previous activity to compare')
  assert.equal(comparison(3, 2), '+50.0% vs previous period')
  assert.equal(comparison(0, 4), '-100.0% vs previous period')
})
test('csv escapes quotes and neutralizes spreadsheet formulas', () => {
  for (const value of ['=SUM(1)', '+1', '-2', '@test', '  =1', '\tfoo']) assert.ok(csvCell(value).startsWith('"\''))
  assert.equal(csvCell('Gym "A", city'), '"Gym ""A"", city"')
  assert.equal(analyticsCsv(['Gym', 'Bookings'], [['A', 0]]), '\uFEFF"Gym","Bookings"\r\n"A","0"')
})
test('filters preserve unspecified-location selection and use abortable read-only API', async () => {
  const filters = { date_from: '2026-11-01', date_to: '2026-11-10', grain: 'week', city: '', state: 'A & B', gym_id: undefined }
  assert.equal(analyticsQuery(filters), 'date_from=2026-11-01&date_to=2026-11-10&grain=week&city=&state=A+%26+B')
  let call; globalThis.analyticsRequest = (...args) => { call = args }
  const signal = new AbortController().signal
  await analyticsService.report(filters, signal)
  assert.equal(call[1].signal, signal); assert.equal(call[1].cache, 'no-store'); assert.equal(call[1].method, undefined)
})