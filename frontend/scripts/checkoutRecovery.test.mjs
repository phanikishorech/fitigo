import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const source = readFileSync(new URL('../src/utils/checkoutRecovery.ts', import.meta.url), 'utf8')
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { checkoutMessage, pendingCartCheckout } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

test('booking expiry explains blocked payment without declaring financial failure', () => {
  const message = checkoutMessage({ status: 'PENDING', can_pay: false, payment_blocked_reason: 'BOOKING_EXPIRED' })
  assert.match(message, /Booking payment window expired/)
  assert.match(message, /does not mean the payment failed/)
  assert.doesNotMatch(message, /You can retry/)
})
test('processing, unavailable session and old cancellation have safe recovery messages', () => {
  for (const reason of ['PAYMENT_PROCESSING', 'ORDER_UNRESOLVED', 'SESSION_UNAVAILABLE', 'GATEWAY_UNAVAILABLE', 'BOOKING_UNAVAILABLE']) {
    const message = checkoutMessage({ status: 'FAILED', can_pay: false, payment_blocked_reason: reason })
    assert.doesNotMatch(message, /You can retry/)
    assert.ok(message.length > 30)
  }
})
test('cart recovery excludes settled records, but keeps unresolved local cancellations', () => {
  const old = { id: 'old', kind: 'CART', status: 'CANCELLED', replacement_safe: false }
  const pending = { id: 'pending', kind: 'CART', status: 'PENDING' }
  const records = [{ id: 'paid', kind: 'CART', status: 'PAID' }, { kind: 'WALLET_TOPUP', status: 'PENDING' }, old, pending]
  assert.equal(pendingCartCheckout(records), pending)
  assert.equal(pendingCartCheckout(records.slice(0, -1)), old)
  assert.equal(pendingCartCheckout([{ ...old, replacement_safe: true }]), undefined)
})

test('paid but unfulfilled clearly distinguishes booking review from unpaid', () => {
  const message = checkoutMessage({ status: 'REVIEW_REQUIRED', failure_code: 'FULFILLMENT_UNAVAILABLE' })
  assert.match(message, /Payment received, but the booking could not be confirmed/)
  assert.match(message, /Do not pay again/)
})

test('replaced orders never resume or pretend to be cancelled at the gateway', () => {
  const row = { kind: 'CART', status: 'SUPERSEDED' }
  assert.equal(pendingCartCheckout([row]), undefined)
  assert.match(checkoutMessage(row), /gateway order was not cancelled/)
})

test('cancellation request is not safe closure or a wallet release', () => {
  const message = checkoutMessage({ status: 'FAILED', payment_blocked_reason: 'CANCELLATION_PENDING', wallet_status: 'HELD' })
  assert.match(message, /do not pay again/)
  assert.match(message, /stay reserved/)
  assert.doesNotMatch(message, /safely cancelled/)
  assert.match(checkoutMessage({ status: 'CANCELLED', replacement_safe: true, wallet_status: 'RELEASED' }), /safely cancelled/)
})