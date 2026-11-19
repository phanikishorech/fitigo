import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const read = name => readFileSync(new URL('../src/' + name, import.meta.url), 'utf8')
async function load(name) { const code = ts.transpileModule(read(name), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText; return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`) }
const membership = await load('utils/membership.ts')
test('transferred membership is historical, not current access', () => {
  assert.equal(membership.membershipOverviewState([{ status: 'TRANSFERRED' }], null), 'none')
  assert.deepEqual(membership.groupMembershipRecords([{ id: 1, status: 'TRANSFERRED' }, { id: 2, status: 'ACTIVE' }]), { history: [{ id: 1, status: 'TRANSFERRED' }], current: [{ id: 2, status: 'ACTIVE' }] })
})
test('customer cancellation UI uses backend policy and explicit wallet-only confirmation', () => {
  const component = read('components/booking/BookingCancellation.tsx')
  assert.match(component, /policy\.eligible/); assert.match(component, /policy\.deadline/)
  assert.match(component, /policy\.refundable_amount/); assert.match(component, /not your original payment method/)
  assert.match(component, /Confirm cancellation/); assert.doesNotMatch(component, /Date\.now|setHours|3 \* 60/)
  assert.doesNotMatch(read('pages/booking/BookingDetailPage.tsx'), /const canCancel|slot_date >= localDate/)
})
test('transfer confirmation is explicit, idempotent and excludes recipient credentials', () => {
  const source = read('components/membership/MembershipTransfer.tsx')
  assert.match(source, /Idempotency-Key/); assert.match(source, /confirmed: true/)
  assert.match(source, /disabled=\{!confirmed\}/); assert.match(source, /confirmation_token/)
  assert.match(source, /setPreview\(null\)/); assert.doesNotMatch(source, /password|otp/i)
  assert.match(source, /remaining_valid_until/)
})
test('single-gym cards never show transfer or cancellation controls', () => {
  const page = read('pages/membership/MembershipOverview.tsx')
  const single = page.slice(page.indexOf('function SingleMembershipCard'), page.indexOf('function MembershipLinks'))
  assert.doesNotMatch(single, /MembershipTransfer|Cancel Membership|Transfer Membership/)
  assert.match(page, /membership\.membership_type === 'MULTI_GYM'/)
})