import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
const source = readFileSync(new URL('../src/utils/paymentReturn.ts', import.meta.url), 'utf8')
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { paymentReturnReference, rememberPaymentReturn, storedPaymentReturn, clearPaymentReturn } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
const id = '11111111-2222-4333-8444-555555555555', provider = `fitigo_${id.replaceAll('-', '')}`
test('explicit and legacy Cashfree return references resolve to an exact checkout', () => {
  for (const query of [`payment_checkout_id=${id}`, `order_id=${provider}`, `payment_checkout_id=${id}&order_id=${provider}&status=SUCCESS`]) assert.deepEqual(paymentReturnReference(query), { requested: true, checkoutId: id })
  assert.deepEqual(paymentReturnReference(''), { requested: false, checkoutId: null })
  assert.deepEqual(paymentReturnReference('status=SUCCESS'), { requested: false, checkoutId: null })
})
test('malformed, conflicting and duplicate references fail closed', () => {
  for (const query of ['payment_checkout_id=bad', 'order_id=bad', `payment_checkout_id=${id}&order_id=fitigo_${'0'.repeat(32)}`, `payment_checkout_id=${id}&payment_checkout_id=${id}`, 'order_id=']) assert.deepEqual(paymentReturnReference(query), { requested: true, checkoutId: null })
})
test('legacy tab fallback is customer scoped, expiring and contains no payment data', () => {
  const data = new Map()
  globalThis.sessionStorage = { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key) }
  rememberPaymentReturn(1, id)
  assert.equal(storedPaymentReturn(1), id)
  assert.equal(storedPaymentReturn(2), null)
  const value = JSON.parse(data.get('fitigo:payment-return'))
  assert.deepEqual(Object.keys(value).sort(), ['at', 'checkoutId', 'userId'])
  data.set('fitigo:payment-return', JSON.stringify({ ...value, at: Date.now() - 3600001 }))
  assert.equal(storedPaymentReturn(1), null)
  rememberPaymentReturn(1, id); clearPaymentReturn(id)
  assert.equal(storedPaymentReturn(1), null)
})