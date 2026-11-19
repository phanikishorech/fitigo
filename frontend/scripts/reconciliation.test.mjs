import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const source = read('../src/admin/reconciliationService.ts').replace(/import \{ request \}[^\n]+/, 'const request=(...args)=>globalThis.reconciliationRequest(...args)')
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { reconciliationService: service } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
test('reconciliation isolates environment, gym, view and page', async () => {
  let args; globalThis.reconciliationRequest = async (...value) => { args = value }
  await service.report('live', 'sources', 7, 2)
  assert.equal(args[0], '/admin/financial-reconciliation?mode=live&view=sources&gym_id=7&limit=20&offset=40')
  assert.equal(args[1].cache, 'no-store')
})
test('review decision sends immutable retry body, optimistic revision and impact hash', async () => {
  let args; globalThis.reconciliationRequest = async (...value) => { args = value }
  const body = { mode: 'test', expected_revision: 3, expected_impact_hash: 'a'.repeat(64), status: 'NEEDS_EVIDENCE', acknowledge_no_execution: true }
  await service.decide('case-id', body, 'same-review-key')
  assert.equal(args[1].headers['Idempotency-Key'], 'same-review-key')
  assert.deepEqual(JSON.parse(args[1].body), body)
  assert.equal(args[0], '/admin/financial-reconciliation/reviews/case-id/decisions')
})
test('trace inspection is read-only and environment scoped', async () => {
  let args; globalThis.reconciliationRequest = async (...value) => { args = value }
  await service.record('live', 'source', 'source-id')
  assert.equal(args[0], '/admin/financial-reconciliation/records/source/source-id?mode=live')
  assert.equal(args[1].method, undefined)
})
test('dashboard labels unknown, page scope and non-executing review', () => {
  const view = read('../src/admin/FinancialReconciliation.tsx')
  assert.match(view, /Unknown \/ unresolved/)
  assert.match(view, /Current page totals only/)
  assert.match(view, /Multi-Gym collections are not FitiGo revenue/)
  assert.match(view, /No financial correction is executed here/)
  assert.doesNotMatch(view, /enableGate|activateWorker|initiateTransfer/)
  assert.match(view, /TraceActions row/)
})
test('settlement editor has unconfigured choices and no fee double deduction', () => {
  const view = read('../src/admin/SettlementSettingsEditor.tsx')
  assert.match(view, /Not configured/)
  assert.match(view, /Explicitly no deductions/)
  assert.match(view, /cannot be deducted again/)
  assert.doesNotMatch(view, /defaultValue=/)
})
test('technical reconciliation route is not mounted in everyday Admin', async () => {
  const code = ts.transpileModule(read('../src/admin/routes.ts'), { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText
  const { adminRoute } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
  assert.equal(adminRoute('/admin/financial-reconciliation').page, 'notFound')
})