import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const source = read('../src/admin/agreementService.ts').replace(/import \{ request \}[^\n]+/, 'const request=(...args)=>globalThis.agreementRequest(...args)')
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { shareValid, agreementService } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
for (const [gym, fitigo, valid] of [['85', '15', true], ['80.25', '19.75', true], ['0', '100', true], ['100', '0', true], ['85', '10', false], ['100.01', '0', false], ['-1', '101', false], ['85.001', '14.999', false], ['', '', false], ['NaN', '100', false]]) {
  test(`sharing validation ${gym}/${fitigo}`, () => assert.equal(shareValid({ gym_percent: gym, fitigo_percent: fitigo }), valid))
}
test('agreement reads preserve environment scope and pagination', async () => {
  let captured; globalThis.agreementRequest = async (...args) => { captured = args; return {} }
  await agreementService.get('live', 7, 2)
  assert.equal(captured[0], '/admin/financial-agreements?mode=live&gym_id=7&limit=20&offset=40')
  assert.equal(captured[1].cache, 'no-store')
})
test('save sends the versioned payload unchanged with retry key', async () => {
  let captured; globalThis.agreementRequest = async (...args) => { captured = args; return {} }
  const payload = { mode: 'test', gym_id: null, expected_version: 3, terms: { fixture: 'exact' } }
  await agreementService.create(payload, 'same-retry-key')
  assert.equal(captured[0], '/admin/financial-agreements')
  assert.equal(captured[1].method, 'POST')
  assert.equal(captured[1].headers['Idempotency-Key'], 'same-retry-key')
  assert.deepEqual(JSON.parse(captured[1].body), payload)
})
test('admin UI uses stored proposal, review and existing navigation', () => {
  const component = read('../src/admin/RevenueSharingSettings.tsx')
  assert.match(component, /config.template/); assert.match(component, /Review new agreement version/)
  assert.match(component, /reason/); assert.match(component, /CA approval reference/)
  assert.match(component, /expected_version/); assert.match(component, /crypto.randomUUID/)
  assert.doesNotMatch(component, /['"]85(?:\.00)?['"]|['"]70(?:\.00)?['"]|['"]500(?:\.00)?['"]/)
  assert.match(read('../src/admin/WorkflowSettings.tsx'), /\/admin\/financial-settings/)
})