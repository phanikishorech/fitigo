import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const code = ts.transpileModule(readFileSync(new URL('../src/utils/paymentHistory.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }
}).outputText
const { historyAction, historyStatus, historyStatuses, paymentHistoryNotice, purchasePresentation } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

test('payment history uses human-readable purchases without changing filter keys', () => {
  assert.equal(purchasePresentation('MULTI_GYM').label, 'Multi-gym membership')
  assert.equal(purchasePresentation('WALLET_TOPUP').value, 'WALLET_TOPUP')
  assert.equal(purchasePresentation('CART').label, 'Gym visits')
  assert.equal(purchasePresentation('FUTURE_KIND').label, 'Future kind')
})
test('every payment status has a text label; only paid/success are successful', () => {
  for (const status of historyStatuses) {
    assert.ok(historyStatus(status).label)
    assert.equal(historyStatus(status).tone === 'success', status === 'PAID')
  }
  assert.equal(historyStatus('SUPERSEDED').label, 'Replaced')
  assert.equal(historyStatus('PARTIALLY_REFUNDED').label, 'Partially refunded')
  assert.equal(historyStatus('UNRECOGNIZED').tone, 'neutral')
})
test('paid and terminal records never invite resume/retry', () => {
  for (const status of ['PAID', 'REFUNDED', 'PARTIALLY_REFUNDED', 'SUPERSEDED', 'REVIEW_REQUIRED', 'CANCELLED']) {
    assert.equal(historyAction(status), 'Check payment status')
  }
  assert.equal(historyAction('PENDING'), 'Manage payment')
})
test('review and replaced notices do not fabricate cancellation or settlement', () => {
  assert.match(paymentHistoryNotice('REVIEW_REQUIRED', 'FULFILLMENT_UNAVAILABLE'), /Payment received/)
  assert.match(paymentHistoryNotice('REVIEW_REQUIRED', 'PAYMENT_AMOUNT_MISMATCH'), /different paid amount/)
  assert.match(paymentHistoryNotice('REVIEW_REQUIRED', null), /Do not pay again/)
  assert.match(paymentHistoryNotice('SUPERSEDED', null), /not cancelled at the gateway/)
  assert.equal(paymentHistoryNotice('PAID', null), null)
})
test('history keeps existing font/theme and does not initiate gateway payment or cancellation directly', () => {
  const page = readFileSync(new URL('../src/pages/profile/PaymentHistory.tsx', import.meta.url), 'utf8')
  const css = readFileSync(new URL('../src/pages/profile/paymentHistory.css', import.meta.url), 'utf8')
  assert.doesNotMatch(css, /font-family|@import|https?:/)
  assert.match(css, /var\(--fg-green\)/)
  assert.match(page, /paymentService.refresh/)
  assert.match(page, /<GatewayPayment/)
  assert.doesNotMatch(page, /paymentService\.(create|cancel)|openPayment\(/)
  assert.match(page, /a.currency \|\| row.currency/)
  assert.match(page, /b.currency \|\| row.currency/)
})