import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
const source = readFileSync(new URL('../src/utils/paymentRecovery.ts', import.meta.url), 'utf8')
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { paymentRecoverySummary, paymentSupportDraft } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
const checkout = { id: 'checkout-original', order_reference: 'original-order', payment_reference: 'pay_original', gateway_order_id: 'order_original', status: 'FAILED', recovery_status: 'RESOLUTION_REQUIRED', payment_blocked_reason: 'WALLET_HOLD_RECONCILING', wallet_status: 'HELD', wallet_amount: '49.00', total_amount: '2199.00', amount: '2150.00', gateway_amount: '2150.00', currency: 'INR', mode: 'test' }
test('expired failed payment is unresolved, never closed or retryable by inference', () => {
  const result = paymentRecoverySummary(checkout)
  assert.equal(result.title, 'Payment resolution required')
  assert.match(result.message, /does not close the payment/)
  assert.match(result.message, /reserved, not charged/)
  assert.doesNotMatch(result.message, /can resume|safely closed/)
})
test('explicit backend resume capability explains same-order recovery, not replacement', () => {
  const result = paymentRecoverySummary({ ...checkout, can_resume_reserved_membership: true })
  assert.equal(result.title, 'Original payment can be resumed')
  assert.match(result.message, /same order/)
  assert.match(result.message, /does not start payment for a different plan/)
})
test('authoritative states distinguish closure, processing and cancellation', () => {
  for (const [state, title] of [['PAID', 'Payment confirmed'], ['SAFELY_CLOSED', 'Checkout safely closed'], ['PROCESSING', 'Confirming your payment'], ['CANCELLATION_PENDING', 'Cancellation pending'], ['REVIEW_REQUIRED', 'Payment needs review'], ['RESUMABLE', 'Payment attempt failed']]) {
    assert.equal(paymentRecoverySummary({ ...checkout, recovery_status: state }).title, title)
  }
  assert.equal(paymentRecoverySummary({ ...checkout, recovery_status: undefined }).title, 'Payment resolution required')
})
test('support draft includes original references and amounts but excludes secrets', () => {
  const draft = paymentSupportDraft({ ...checkout, key_id: 'SECRET_KEY', payment_session_id: 'SECRET_SESSION', razorpay_signature: 'SECRET_SIGNATURE' })
  for (const value of ['checkout-original', 'original-order', 'pay_original', 'order_original', '2199.00', '49.00', '2150.00', 'RESOLUTION_REQUIRED']) assert.ok(draft.body.includes(value))
  assert.doesNotMatch(JSON.stringify(draft), /SECRET/)
  assert.match(draft.body, /does not authorize a wallet release/)
  assert.ok(draft.body.length <= 2000)
})