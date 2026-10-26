import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

async function load(path, transform = s => s) {
  const source = transform(readFileSync(new URL(path, import.meta.url), 'utf8'))
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
}
const { paymentService } = await load('../src/services/paymentService.ts', s => s.replace(/import .* from '.\/client'/, `const request=(...args)=>globalThis.__paymentRequest(...args);const post=(path,body)=>request(path,{method:'POST',body:JSON.stringify(body)})`))
const { openRazorpay } = await load('../src/utils/razorpay.ts')
const checkout = { id: 'local', can_pay: true, key_id: 'rzp_test_fixture', mode: 'test', razorpay_order_id: 'order_fixture', amount_minor: 12345, currency: 'INR' }

test('payment APIs send source IDs and stable keys, not browser amounts', async () => {
  const calls = []; globalThis.__paymentRequest = async (...args) => { calls.push(args); return checkout }
  await paymentService.create({ kind: 'BOOKING', booking_id: 7 }, 'stable-key')
  await paymentService.create({ kind: 'BOOKING', booking_id: 7 }, 'stable-key')
  assert.equal(calls[0][1].headers['Idempotency-Key'], 'stable-key')
  assert.deepEqual(JSON.parse(calls[0][1].body), { kind: 'BOOKING', booking_id: 7 })
  assert.deepEqual(calls[0], calls[1])
  await paymentService.refresh('local')
  assert.equal(calls[2][0], '/payments/checkouts/local/refresh')
})
test('checkout success is a callback only; server verification is still required', async () => {
  let options
  const callback = { razorpay_order_id: 'order_fixture', razorpay_payment_id: 'pay_fixture', razorpay_signature: 'signature' }
  globalThis.window = { Razorpay: class { constructor(value) { options = value } on() {} open() { options.handler(callback) } } }
  assert.deepEqual(await openRazorpay(checkout), { type: 'success', callback })
  assert.equal(options.amount, 12345); assert.equal(options.order_id, 'order_fixture')
  assert.equal(options.key, 'rzp_test_fixture'); assert.equal(options.retry.enabled, false)
})
test('customer dismissal is not a successful payment', async () => {
  let options
  globalThis.window = { Razorpay: class { constructor(value) { options = value } on() {} open() { options.modal.ondismiss() } } }
  assert.deepEqual(await openRazorpay(checkout), { type: 'cancelled' })
})
test('failure event wins over following dismiss and never confirms payment', async () => {
  let options, failure
  globalThis.window = { Razorpay: class { constructor(value) { options = value } on(event, fn) { assert.equal(event, 'payment.failed'); failure = fn } open() { failure() } close() { options.modal.ondismiss() } } }
  assert.deepEqual(await openRazorpay(checkout), { type: 'failed' })
})
test('invalid mode or unavailable checkout cannot open the gateway', async () => {
  await assert.rejects(openRazorpay({ ...checkout, key_id: 'rzp_live_wrong' }))
  await assert.rejects(openRazorpay({ ...checkout, can_pay: false }))
})
test('existing checkout and membership pages use shared gateway integration', () => {
  for (const path of ['../src/pages/booking/CartPage.tsx', '../src/pages/membership/MembershipPage.tsx', '../src/pages/membership/MembershipOrderPage.tsx']) {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8')
    assert.match(source, /GatewayPayment/)
    assert.doesNotMatch(source, /RAZORPAY_KEY_SECRET|RAZORPAY_WEBHOOK_SECRET/)
  }
  const component = readFileSync(new URL('../src/components/common/GatewayPayment.tsx', import.meta.url), 'utf8')
  assert.match(component, /paymentService.verify/); assert.match(component, /next.status === 'PAID'/)
})