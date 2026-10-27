import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const compile = source => `data:text/javascript;base64,${Buffer.from(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText).toString('base64')}`
globalThis.__membershipUtils = await import(compile(read('../src/utils/membership.ts')))
const { memberHomePresentation } = await import(compile(read('../src/utils/memberHome.ts').replace(/import .* from '.\/membership'/, 'const {dayPresentation,todayFrom}=globalThis.__membershipUtils')))
const summary = { membership_id: 1, status: 'ACTIVE', membership_scope: 'MULTI_GYM', active_gyms: [] }
const calendar = { access_type: 'MULTI_GYM', gym: null, days: [{ status: 'TODAY', qr_status: 'ACTIVE', qr_available: true, date: '2026-10-27' }] }
test('active FitiGo member gets an invitation to My Access, not a new purchase', () => {
  const result = memberHomePresentation(summary, calendar)
  assert.equal(result.title, 'You’re a FitiGo member')
  assert.equal(result.action, 'Book a visit today')
})
test('single gym member sees the authoritative gym name', () => {
  const result = memberHomePresentation({ ...summary, membership_scope: 'SINGLE_GYM', active_gyms: [{ gym_name: 'My Gym' }] }, { ...calendar, access_type: 'SINGLE_GYM', gym: { id: 1, name: 'My Gym' } })
  assert.equal(result.title, 'You’re a member of My Gym')
})
test('used paused revoked or unavailable access never invites another visit', () => {
  for (const status of ['USED', 'PAUSED', 'REVOKED', 'NO_ACCESS', 'EXPIRED']) {
    const result = memberHomePresentation(summary, { ...calendar, days: [{ ...calendar.days[0], qr_status: status, qr_available: false }] })
    assert.notEqual(result.action, 'Book a visit today')
  }
  assert.equal(memberHomePresentation({ ...summary, status: 'PAUSED' }, calendar).status, 'Paused')
})
test('expired absent and unmatched memberships are never advertised as active', () => {
  for (const status of ['EXPIRED', 'CANCELLED', null, 'UNKNOWN']) assert.equal(memberHomePresentation({ ...summary, status }, calendar), null)
  assert.equal(memberHomePresentation({ ...summary, membership_id: null }, calendar), null)
  assert.equal(memberHomePresentation(summary, { ...calendar, days: [] }), null)
})
test('home card is authenticated customer-only and read-only', () => {
  const card = read('../src/components/membership/HomeMembershipCard.tsx')
  assert.match(card, /session.status !== 'authenticated'/)
  assert.match(card, /key=\{session.identity.user.id\}/)
  assert.match(card, /to="\/my-access"/)
  assert.match(card, /validateAccessCalendar/)
  assert.doesNotMatch(card, /accessService.today|paymentService|bookingService/)
  assert.match(read('../src/pages/discovery/DiscoveryPage.tsx'), /home && <HomeMembershipCard/)
})