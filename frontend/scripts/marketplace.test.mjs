import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
const root = new URL('../src/admin/', import.meta.url)
const read = name => readFileSync(new URL(name, root), 'utf8')
test('existing FinancialOverview embeds commercial ledger without changing statutory recognition', () => {
  const source = read('FinancialOverview.tsx')
  assert.match(source, /MarketplaceFinancials/)
  assert.match(source, /Multi-Gym recognized revenue/)
  assert.match(source, /Unknown/)
})
test('marketplace filters and source drilldowns remain explicit', () => {
  const source = read('MarketplaceFinancials.tsx')
  for (const value of ['owner_user_id', 'category', 'agreement_version', 'payment_references', 'visitor_index', 'fee_pending_count']) assert.ok(source.includes(value), value)
  assert.match(source, /value == null \? 'Unavailable'/)
  assert.match(source, /Policy missing — no leftover-value recognition/)
})
test('payout UI requires evidence and immutable retry payload', () => {
  const source = read('MarketplaceFinancials.tsx')
  assert.match(source, /request.current/)
  assert.match(source, /setAttempted\(true\)/)
  assert.match(source, /document_reference/)
  assert.match(source, /No bank transfer is initiated/)
  assert.doesNotMatch(source, /\*\s*0\.85|\*\s*0\.15|Math\.round/)
})
test('payout mutations carry idempotency and optimistic versions', () => {
  const source = read('marketplaceService.ts')
  assert.match(source, /Idempotency-Key/)
  assert.match(source, /expected_version: row.version/)
  assert.match(source, /cache: 'no-store'/)
})