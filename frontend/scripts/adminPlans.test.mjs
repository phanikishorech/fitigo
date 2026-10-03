import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

async function load(path, replace = value => value) {
  const source = replace(readFileSync(new URL(path, import.meta.url), 'utf8'))
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`)
}
const routes = await load('../src/admin/routes.ts')
const services = await load('../src/admin/membershipPlanService.ts', source => source
  .replace(/import .* from '..\/services\/client'/, `class ApiError extends Error {}; const request=(...args)=>globalThis.__planAdminRequest(...args);`)
  .replace(/import .* from '.\/services'/, `const adminError=()=> 'safe error';`))
for (const [path, page] of Object.entries({ '/admin/membership-plans': 'membership-plans', '/admin/membership-plans/new': 'plan-new', '/admin/membership-plans/5': 'plan-edit', '/admin/membership-plans/5/offer': 'plan-offer' })) {
  test(`admin plan route ${path}`, () => { assert.equal(routes.adminRoute(path).page, page); assert.equal(routes.adminReturnTo(path), path) })
}
test('invalid plan routes fail closed', () => {
  for (const path of ['/admin/membership-plans/0', '/admin/membership-plans/-3', '/admin/membership-plans/9007199254740992', '/admin/membership-plans/new/offer', '/admin/membership-plans/3/review']) assert.equal(routes.adminRoute(path).page, 'notFound')
})
test('editable plan copies only accepted configuration fields, preserving full replacements', () => {
  const input = { code:'test', name:'Test', description:null, duration_value:7, duration_unit:'DAY', base_price:'120.00', currency:'INR', benefits:['Benefit'], badge:'Badge', display_order:0, is_active:false }
  const actual = services.editablePlan({ ...input, id:5, final_price:'90.00', offer:{}, version:3 })
  assert.deepEqual(actual, input)
  actual.benefits.push('New')
  assert.deepEqual(input.benefits, ['Benefit'])
})
test('admin plan service sends real endpoints and optimistic version, never final pricing', async () => {
  const calls=[]; globalThis.__planAdminRequest = async (...args) => { calls.push(args); return {} }
  await services.adminMembershipPlans.list()
  await services.adminMembershipPlans.detail(5)
  await services.adminMembershipPlans.create({name:'Test'})
  await services.adminMembershipPlans.update(5, {name:'Test',base_price:'400.00'}, 7)
  await services.adminMembershipPlans.offer(5, {kind:'FIXED',value:'30.00',expected_version:8})
  assert.deepEqual(calls.map(call=>call[0]), ['/admin/membership-plans','/admin/membership-plans/5','/admin/membership-plans','/admin/membership-plans/5','/admin/membership-plans/5/offer'])
  assert.equal(calls[1][1].cache,'no-store')
  assert.deepEqual(JSON.parse(calls[3][1].body),{name:'Test',base_price:'400.00',expected_version:7})
  assert.equal(JSON.parse(calls[4][1].body).expected_version,8)
})
test('explicit UTC editor round trips offsets and seconds without local timezone conversion', () => {
  assert.equal(services.utcInput('2026-10-10T10:30:45+05:30'),'2026-10-10T05:00:45')
  assert.equal(services.utcValue('2026-10-10T05:00:45'),'2026-10-10T05:00:45.000Z')
})