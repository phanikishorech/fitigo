import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const path = '../src/services/platformMembershipService.ts'
const source = readFileSync(new URL(path, import.meta.url), 'utf8').replace(/import .* from '.\/client'/, `class ApiError extends Error {}; const request=(...args)=>globalThis.__platformRequest(...args);`)
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { platformMembershipService: service, planDuration } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

test('platform catalog uses the real centralized endpoint with no cached prices', async () => {
  let call
  globalThis.__platformRequest = async (...args) => { call = args; return { items: [] } }
  assert.deepEqual(await service.catalog(), { items: [] })
  assert.equal(call[0], '/memberships/plans?membership_type=MULTI_GYM')
  assert.equal(call[1].cache, 'no-store')
})
test('order submission contains only plan ID and reuses idempotency key', async () => {
  const calls = []
  globalThis.__platformRequest = async (...args) => { calls.push(args); return { id: 'order' } }
  await service.createOrder(7, 'stable-key')
  await service.createOrder(7, 'stable-key')
  assert.equal(calls[0][0], '/memberships/orders')
  assert.deepEqual(JSON.parse(calls[0][1].body), { plan_id: 7 })
  assert.equal(calls[0][1].headers['Idempotency-Key'], 'stable-key')
  assert.deepEqual(calls[0], calls[1])
})
test('duration is a rendering of server data, not a fixed plan list', () => {
  assert.equal(planDuration({ duration_value: 7, duration_unit: 'DAY' }), '7 days')
  assert.equal(planDuration({ duration_value: 1, duration_unit: 'MONTH' }), '1 month')
  assert.equal(planDuration({ duration_value: 2, duration_unit: 'YEAR' }), '2 years')
})
test('order review uses wallet-only checkout and no external or dummy activation', () => {
  const page = readFileSync(new URL('../src/pages/membership/MembershipOrderPage.tsx', import.meta.url), 'utf8')
  assert.match(page, /WalletMembershipPayment/)
  assert.match(page, /platformMembershipService.payWallet/)
  assert.doesNotMatch(page, /payment-session|membershipService.purchase|Confirm MVP/)
})
test('wallet payment accepts only the reviewed server fingerprint, not a client price', async () => {
  let call
  globalThis.__platformRequest = async (...args) => { call=args;return {} }
  await service.payWallet('test-order', 'server-quote')
  assert.equal(call[0], '/memberships/orders/test-order/pay-wallet')
  assert.deepEqual(JSON.parse(call[1].body),{accepted_quote:'server-quote'})
})