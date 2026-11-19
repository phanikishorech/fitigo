import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const source = readFileSync(new URL('../src/admin/businessService.ts', import.meta.url), 'utf8')
const code = ts.transpileModule(source.replace(/^import .*$/gm, ''), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const service = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
test('verified category amount displays as partial, never a complete total', () => {
  const collections = { complete: false, categories: { individual: null }, known_dated_categories: { individual: '300.00' }, category_complete: { individual: false }, excluded_by_category: { individual: 11 } }
  assert.deepEqual(service.collectionCard(collections, 'individual'), { value: '300.00', partial: true, excluded: 11 })
})
test('a missing category amount never becomes a fabricated zero', () => {
  assert.deepEqual(service.collectionCard({ complete: false, categories: { single_gym: null }, known_dated_categories: { single_gym: '0.00' }, excluded_by_category: { single_gym: 1 } }, 'single_gym'), { value: null, partial: false, excluded: 1 })
})
test('complete category can display independently of incomplete overall total', () => {
  assert.deepEqual(service.collectionCard({ complete: false, categories: { single_gym: '500.00' }, category_complete: { single_gym: true }, excluded_by_category: { single_gym: 0 } }, 'single_gym'), { value: '500.00', partial: false, excluded: 0 })
  assert.deepEqual(service.collectionCard({ complete: true, categories: { multi_gym: '0.00' } }, 'multi_gym'), { value: '0.00', partial: false, excluded: 0 })
})
test('incomplete zero subset does not replace unknown total or reuse earlier scope amount', () => {
  const earlier = { complete: false, categories: { individual: null }, known_dated_categories: { individual: '300.00' }, excluded_by_category: { individual: 11 } }
  assert.equal(service.collectionCard(earlier, 'individual').value, '300.00')
  const today = { ...earlier, known_dated_categories: { individual: '0.00' } }
  assert.deepEqual(service.collectionCard(today, 'individual'), { value: null, partial: false, excluded: 11 })
  assert.equal(service.collectionCard(earlier, 'individual').value, '300.00')
})
test('dashboard exposes collection basis beside the partial subtotal', () => {
  const view = readFileSync(new URL('../src/admin/BusinessOverview.tsx', import.meta.url), 'utf8')
  const partial = view.slice(view.indexOf('title="Verified collections — partial subtotal"'), view.indexOf('{data.collections.exclusion_reasons'))
  assert.ok(partial.includes('data.definitions.collections'))
  assert.ok(partial.includes('data.date_from') && partial.includes('data.date_to'))
})