import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

async function load(path, transform = s => s) {
  const source = transform(readFileSync(new URL(path, import.meta.url), 'utf8'))
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
}
const { openCashfree } = await load('../src/utils/cashfree.ts')
const { openPayment } = await load('../src/utils/paymentGateway.ts', s => s
  .replace(/import \{ openRazorpay \}[^\n]+/, `const openRazorpay=()=> 'razorpay'`)
  .replace(/import \{ openCashfree \}[^\n]+/, `const openCashfree=()=> 'cashfree'`))
const checkout = { provider: 'CASHFREE', environment: 'sandbox', mode: 'test', can_pay: true, payment_session_id: 'session_fixture' }

test('Cashfree uses backend session and environment; SDK completion is not paid', async () => {
  let options, invocation
  globalThis.window = { Cashfree: config => { options = config; return { checkout: async input => { invocation = input; return { paymentDetails: 'untrusted' } } } } }
  assert.deepEqual(await openCashfree(checkout), { type: 'returned' })
  assert.deepEqual(options, { mode: 'sandbox' })
  assert.deepEqual(invocation, { paymentSessionId: 'session_fixture', redirectTarget: '_modal' })
})
test('Cashfree dismissal/error requires reconciliation, never success', async () => {
  globalThis.window = { Cashfree: () => ({ checkout: async () => ({ error: { message: 'closed' } }) }) }
  assert.deepEqual(await openCashfree(checkout), { type: 'cancelled' })
})
test('Cashfree unavailable or inconsistent environment fails closed', async () => {
  for (const changes of [{ can_pay: false }, { environment: 'production' }, { payment_session_id: null }, { provider: 'OTHER' }]) {
    await assert.rejects(openCashfree({ ...checkout, ...changes }))
  }
})
test('factory selects the backend provider with no failure fallback', () => {
  assert.equal(openPayment(checkout), 'cashfree')
  assert.equal(openPayment({ provider: 'RAZORPAY' }), 'razorpay')
  assert.throws(() => openPayment({ provider: 'OTHER' }))
})
test('both memberships and individual bookings support Cashfree in existing UI', () => {
  for (const path of ['../src/pages/booking/BookingAccess.tsx', '../src/pages/membership/MembershipPage.tsx', '../src/pages/membership/MembershipOrderPage.tsx']) {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8')
    assert.match(source, /CASHFREE/); assert.match(source, /GatewayPayment/)
  }
  const source = readFileSync(new URL('../src/components/common/GatewayPayment.tsx', import.meta.url), 'utf8')
  assert.match(source, /paymentService.verify/)
  assert.match(source, /paymentService.refresh/)
  assert.doesNotMatch(source, /CASHFREE_CLIENT_SECRET|RAZORPAY_KEY_SECRET/)
})