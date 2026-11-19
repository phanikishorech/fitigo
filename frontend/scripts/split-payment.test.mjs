import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('../src/services/paymentService.ts', import.meta.url), 'utf8')
  .replace(/import \{ post, request \}[^\n]+/, 'const post=(...args)=>globalThis.paymentTransport.post(...args); const request=(...args)=>globalThis.paymentTransport.request(...args)')
  .replace(/import \{ cartMutation \}[^\n]+/, 'const cartMutation=value=>value')
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { paymentService } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

test('funding quote sends source and wallet preference only, returning server breakdown unchanged', async () => {
  const selection = { kind: 'CART', cart_item_ids: [1, 2], use_wallet: true, wallet_amount: '20.00' }
  const breakdown = { total_amount: '150.00', wallet_amount: '20.00', gateway_amount: '130.00' }
  globalThis.paymentTransport = { post: async (path, body) => { assert.equal(path, '/payments/quote'); assert.deepEqual(body, selection); return breakdown } }
  assert.equal(await paymentService.quote(selection), breakdown)
})
test('wallet checkout preserves existing create API and idempotency key', async () => {
  const selection = { kind: 'BOOKING', booking_id: 1, use_wallet: true }
  globalThis.paymentTransport = { request: async (path, options) => {
    assert.equal(path, '/payments/checkouts'); assert.equal(options.headers['Idempotency-Key'], 'same-checkout-key')
    assert.deepEqual(JSON.parse(options.body), selection); return { status: 'PAID', gateway_amount: '0.00' }
  } }
  assert.equal((await paymentService.create(selection, 'same-checkout-key')).status, 'PAID')
})
test('Cashfree verification sends no browser payment assertions', async () => {
  globalThis.paymentTransport = { post: async (path, body) => { assert.equal(path, '/payments/checkouts/checkout-id/verify'); assert.deepEqual(body, {}); return { status: 'PENDING' } } }
  assert.equal((await paymentService.verify('checkout-id')).status, 'PENDING')
})
test('wallet selection uses backend quote; zero contribution cannot invoke an SDK from the selector', () => {
  const component = readFileSync(new URL('../src/components/payments/WalletFunding.tsx', import.meta.url), 'utf8')
  assert.match(component, /useState\(false\)/)
  assert.match(component, /paymentService.quote/)
  assert.match(component, /available_wallet_balance/)
  assert.match(component, /quote.wallet_amount/)
  assert.match(component, /quote.gateway_amount/)
  assert.doesNotMatch(component, /openPayment|Razorpay\(|Cashfree\(|Math.min/)
})
test('paid wallet-only result returns before opening external checkout', () => {
  const component = readFileSync(new URL('../src/components/common/GatewayPayment.tsx', import.meta.url), 'utf8')
  assert.ok(component.indexOf('if (!next.can_pay) return') < component.indexOf('await openPayment(next)'))
  assert.match(component, /supportsWallet && !fundingReady/)
})

test('membership recovery is no-store and sends only the purchase identity', async () => {
  globalThis.paymentTransport = { request: async (path, options) => {
    assert.equal(path, '/payments/membership-checkout?kind=MULTI_GYM&order_id=order-1')
    assert.equal(options.cache, 'no-store')
    return { checkout: { id: 'pending', wallet_amount: '49.00' }, matches_selection: true }
  } }
  assert.equal((await paymentService.recoverMembership({ kind: 'MULTI_GYM', order_id: 'order-1', accepted_quote: 'quote', use_wallet: false })).checkout.wallet_amount, '49.00')
})