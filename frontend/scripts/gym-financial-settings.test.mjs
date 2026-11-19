import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const source = read('../src/admin/gymFinancialSettingsService.ts').replace(/import \{ request \}[^\n]+/, 'const request=(...args)=>globalThis.settingsRequest(...args)')
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { gymFinancialSettingsService: service } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

test('gym search encodes literal user input and pagination', async () => {
  let args; globalThis.settingsRequest = async (...value) => { args = value }
  await service.gyms('Gym & 50%', 2)
  assert.equal(args[0], '/admin/financial-settings/gyms?q=Gym+%26+50%25&limit=20&offset=40')
  assert.equal(args[1].cache, 'no-store')
})
test('configuration reads isolate gym, environment and history page', async () => {
  let args; globalThis.settingsRequest = async (...value) => { args = value }
  await service.get('live', 7, 3)
  assert.equal(args[0], '/admin/financial-settings?mode=live&gym_id=7&limit=20&offset=60')
  assert.equal(args[1].cache, 'no-store')
})
test('save preserves exact configuration, optimistic versions and retry key', async () => {
  let args; globalThis.settingsRequest = async (...value) => { args = value }
  const body = { gym_id: 7, mode: 'test', expected_version: 2, expected_effective_version_id: 12, settings: { reference_amount: '3000.00' }, acknowledge_legacy_replacement: true }
  await service.create(body, 'unchanged-request-key')
  assert.equal(args[0], '/admin/financial-settings')
  assert.equal(args[1].method, 'POST')
  assert.equal(args[1].headers['Idempotency-Key'], 'unchanged-request-key')
  assert.deepEqual(JSON.parse(args[1].body), body)
})
test('financial settings is a dedicated route and runtime settings links to it', async () => {
  const routes = ts.transpileModule(read('../src/admin/routes.ts'), { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText
  const { adminRoute, adminReturnTo } = await import(`data:text/javascript;base64,${Buffer.from(routes).toString('base64')}`)
  assert.equal(adminRoute('/admin/financial-settings/').page, 'financial-settings')
  assert.equal(adminReturnTo('/admin/financial-settings'), '/admin/financial-settings')
  assert.match(read('../src/admin/AdminLayout.tsx'), /label: 'Commission Settings'/)
  assert.equal(adminRoute('/admin/commission-settings').page, 'financial-settings')
  assert.match(read('../src/admin/AdminApp.tsx'), /<FinancialSettings \/>/)
  assert.doesNotMatch(read('../src/admin/WorkflowSettings.tsx'), /<RevenueSharingSettings/)
})
test('editor uses backend defaults, explicit review and unknown policies', () => {
  const view = read('../src/admin/FinancialSettings.tsx')
  assert.match(view, /structuredClone\(config.template/)
  assert.match(view, /expected_effective_version_id/)
  assert.match(view, /crypto.randomUUID/)
  assert.match(view, /Monthly amounts become available after verified visits and fees are confirmed/)
  assert.match(view, /divisor, not a cap/)
  assert.match(view, /Saving settings does not send any payment/)
  assert.doesNotMatch(view, /<SettlementSettingsEditor|Processing blockers|JSON.stringify\(row.terms/)
  assert.doesNotMatch(view, /['"]85['"]|['"]3000['"]|fetch\(/)
})
test('both zero-based API pages adapt to the shared one-based pagination control', () => {
  const view = read('../src/admin/FinancialSettings.tsx')
  assert.equal((view.match(/<Pagination page=\{page \+ 1\}/g) || []).length, 2)
  assert.equal((view.match(/onPage=\{value => setPage\(value - 1\)\}/g) || []).length, 2)
})