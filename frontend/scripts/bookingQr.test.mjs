import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const source = readFileSync(new URL('../src/utils/bookingQr.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { hasBookingCheckin, reconcileBookingQr } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
const pass = { qr_id: 99, visitor_name: 'David', status: 'ACTIVE', qr_token: 'GYMACCESS:opaque-fixture', valid_from: '2026-10-09T17:00:00+05:30', expires_at: '2026-10-09T22:00:00+05:30' }
const qr = { booking_id: 42, access_type: 'BOOKING_ACCESS', passes: [pass] }
const used = { qr_id: 99, visitor_name: 'David', status: 'USED', checked_in_at: '2026-10-09T18:00:00+05:30' }
const complete = { status: 'BOOKING_ALREADY_USED', qr_available: false, passes: [used] }

test('successful scan becomes approval with backend check-in time and no QR', () => {
  const next = reconcileBookingQr(qr, complete)
  assert.equal(hasBookingCheckin(next.passes[0]), true)
  assert.equal(next.passes[0].checked_in_at, used.checked_in_at)
  assert.equal(next.passes[0].qr_token, null)
  assert.equal(qr.passes[0].qr_token, pass.qr_token, 'input is immutable')
})
test('group approval leaves only unscanned visitors with active QR', () => {
  const group = { ...qr, passes: [pass, { ...pass, qr_id: 100, visitor_name: 'Mary', qr_token: 'another-token' }] }
  const next = reconcileBookingQr(group, { status: 'READY', qr_available: true, passes: [used, { qr_id: 100, status: 'ACTIVE' }] })
  assert.equal(hasBookingCheckin(next.passes[0]), true)
  assert.equal(next.passes[0].qr_token, null)
  assert.equal(hasBookingCheckin(next.passes[1]), false)
  assert.equal(next.passes[1].qr_token, 'another-token')
})
test('used message without valid matching check-in proof never approves', () => {
  for (const passes of [[], [{ ...used, qr_id: 100 }], [{ ...used, checked_in_at: null }], [{ ...used, checked_in_at: 'invalid' }], [{ ...used, status: 'REVOKED' }]]) {
    assert.equal(reconcileBookingQr(qr, { ...complete, passes }), null)
  }
  assert.equal(reconcileBookingQr({ ...qr, passes: [] }, complete), null)
})
test('cancellation, expiry, failed payment and invalid access cannot become approval', () => {
  for (const status of ['BOOKING_CANCELLED', 'BOOKING_EXPIRED', 'PAYMENT_NOT_COMPLETED', 'INVALID_QR']) {
    assert.equal(reconcileBookingQr(qr, { ...complete, status }), null)
  }
})
test('missing or revoked group pass is hidden, never treated as successful', () => {
  const next = reconcileBookingQr(qr, { status: 'READY', qr_available: true, passes: [] })
  assert.equal(next.passes[0].qr_token, null)
  assert.equal(hasBookingCheckin(next.passes[0]), false)
})