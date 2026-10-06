import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

async function load(path, transform = source => source) {
  const source = transform(readFileSync(new URL(path, import.meta.url), 'utf8'))
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`)
}
const access = await load('../src/services/visitAccessService.ts', source => source
  .replace(/import .* from '.\/accountService'/, 'const accessService = { current: () => globalThis.__visitCalendar() }')
  .replace(/import .* from '.\/gymService'/, 'const gymService = { accessDetails: id => globalThis.__visitGym(id) }')
  .replace(/import .* from '..\/utils\/membership'/, 'const todayFrom = calendar => calendar.days.find(day => day.status === "TODAY")'))
const store = await load('../src/store/bookingStore.ts', source => source
  .replace(/import .* from 'react'/, 'const useSyncExternalStore = () => {}')
  .replace(/import .* from '..\/services\/client'/, 'const localDate = () => "2026-10-01"'))
const gym = { gym_id: 12, membership_access: { status: 'INCLUDED' } }
const today = { date: '2026-10-01', status: 'TODAY', qr_status: 'ACTIVE', qr_available: true }
const calendar = { access_type: 'SINGLE_GYM', gym: { id: 12 }, days: [today] }

test('selected single gym qualifies for a popup; explicit membership choice targets My Access', () => {
  assert.equal(access.visitAccessDecision(gym, calendar), 'MEMBERSHIP')
  assert.equal(access.visitDestination(12, 'MEMBERSHIP'), '/my-access?gymId=12')
})
test('a membership for another single gym never qualifies', () => {
  assert.equal(access.visitAccessDecision(gym, { ...calendar, gym: { id: 99 } }), 'PAID_BOOKING')
})
test('multi-gym requires explicit inclusion for selected gym', () => {
  const multi = { ...calendar, access_type: 'MULTI_GYM', gym: null }
  assert.equal(access.visitAccessDecision(gym, multi), 'MEMBERSHIP')
  assert.equal(access.visitAccessDecision({ ...gym, membership_access: { status: 'NO_ACTIVE_MEMBERSHIP' } }, multi), 'PAID_BOOKING')
})
for (const status of ['NO_ACTIVE_MEMBERSHIP', 'DAY_PASS_AVAILABLE', 'UPGRADE_REQUIRED', 'UNAVAILABLE']) test(`backend gym inclusion ${status} uses existing paid flow`, () => {
  assert.equal(access.visitAccessDecision({ ...gym, membership_access: { status } }, calendar), 'PAID_BOOKING')
  assert.equal(access.visitDestination(12, 'PAID_BOOKING'), '/gyms/12/book/access')
})
for (const status of ['PAUSED', 'EXPIRED', 'NO_ACCESS', 'REVOKED']) test(`today status ${status} uses paid flow, not QR`, () => {
  assert.equal(access.visitAccessDecision(gym, { ...calendar, days: [{ ...today, qr_status: status, qr_available: false }] }), 'PAID_BOOKING')
})
test('already used stays a distinct access state but Book a Visit routes to paid booking', () => {
  assert.equal(access.visitAccessDecision(gym, { ...calendar, days: [{ ...today, qr_status: 'USED', qr_available: false }] }), 'ALREADY_USED')
  assert.equal(access.visitDestination(12, 'ALREADY_USED'), '/gyms/12/book/access')
})
test('unknown or incomplete responses fail closed, never guess paid access', () => {
  for (const value of [
    { ...calendar, days: [] },
    { ...calendar, days: [{ ...today, qr_status: 'UNKNOWN' }] },
    { ...calendar, days: [{ ...today, qr_available: false }] },
    { ...calendar, access_type: 'UNKNOWN' },
    { ...calendar, gym: null }
  ]) assert.throws(() => access.visitAccessDecision(gym, value), /Unable to check/)
  assert.throws(() => access.visitAccessDecision({ ...gym, membership_access: { status: 'UNKNOWN' } }, calendar), /Unable to check/)
})
test('eligibility reads selected gym and read-only calendar, not QR or cart', async () => {
  const calls = []
  globalThis.__visitGym = async id => { calls.push(['gym', id]); return gym }
  globalThis.__visitCalendar = async () => { calls.push(['calendar']); return calendar }
  const result = await access.visitAccessService.check(12)
  assert.deepEqual(calls, [['gym',12],['calendar']]); assert.equal(result.decision,'MEMBERSHIP')
})
test('failed eligibility stays a failure and cannot become a paid decision', async () => {
  globalThis.__visitGym = async () => { throw new Error('API unavailable') }
  globalThis.__visitCalendar = async () => calendar
  await assert.rejects(access.visitAccessService.check(12), /API unavailable/)
})
for (const status of ['NO_ACTIVE_MEMBERSHIP', 'DAY_PASS_AVAILABLE', 'UPGRADE_REQUIRED', 'UNAVAILABLE']) test(`${status} skips the membership calendar and enters existing paid booking`, async () => {
  let calendarCalls = 0
  globalThis.__visitGym = async () => ({ ...gym, membership_access: { status } })
  globalThis.__visitCalendar = async () => { calendarCalls++; throw new Error('No membership found') }
  const result = await access.visitAccessService.check(12)
  assert.equal(result.decision, 'PAID_BOOKING')
  assert.equal(result.calendar, null)
  assert.equal(calendarCalls, 0)
  assert.equal(access.visitDestination(12, result.decision), '/gyms/12/book/access')
})
for (const scope of ['SINGLE_GYM', 'MULTI_GYM']) test(`${scope} covered gym checks available and used access`, async () => {
  globalThis.__visitGym = async () => gym
  for (const state of ['ACTIVE', 'USED']) {
    globalThis.__visitCalendar = async () => ({ ...calendar, access_type: scope, gym: scope === 'MULTI_GYM' ? null : calendar.gym, days: [{ ...today, qr_status: state, qr_available: state === 'ACTIVE' }] })
    assert.equal((await access.visitAccessService.check(12)).decision, state === 'ACTIVE' ? 'MEMBERSHIP' : 'ALREADY_USED')
  }
})
test('included gym calendar errors remain errors, even with a no-membership error message', async () => {
  globalThis.__visitGym = async () => gym
  for (const message of ['No membership found', 'Network error', 'Server error', 'Not found']) {
    globalThis.__visitCalendar = async () => { throw new Error(message) }
    await assert.rejects(access.visitAccessService.check(12), { message })
  }
})
test('unknown/missing eligibility never becomes paid booking or calls the calendar', async () => {
  globalThis.__visitCalendar = async () => { throw new Error('Calendar must not be called') }
  for (const membership_access of [undefined, {}, { status: 'UNKNOWN' }]) {
    globalThis.__visitGym = async () => ({ ...gym, membership_access })
    await assert.rejects(access.visitAccessService.check(12), /Unable to check/)
  }
  assert.throws(() => access.visitAccessDecision(gym, null), /Unable to check/)
})
test('companion draft is independent of normal booking and counts extras only', () => {
  store.updateDraft(12, { memberCount: 4, accessType: 'CLASS', classId: 7 })
  assert.equal(store.getDraft(12, '2026-10-01').memberCount, 1)
  store.updateDraft(12, { memberCount: 2, start: '08:00', end: '09:00', accessType: 'CLASS', date: '2099-01-01', classId: 9 }, '2026-10-01')
  assert.deepEqual(store.getDraft(12, '2026-10-01'), { gymId:12, accessType:'GYM', date:'2026-10-01', memberCount:2, start:'08:00', end:'09:00', classId:null })
  assert.equal(store.getDraft(12).memberCount, 4); assert.equal(store.getDraft(12).accessType,'CLASS')
  assert.equal(store.getDraft(12,'2026-10-02').memberCount,1)
})
test('gym details has the two intended actions and no membership branch UI', () => {
  const source = readFileSync(new URL('../src/pages/discovery/GymPage.tsx', import.meta.url), 'utf8')
  assert.match(source,/Book a Visit/); assert.match(source,/View Membership Plans/)
  assert.doesNotMatch(source,/Generate Visit QR|Book for Others|Use membership access|Visit with your membership/)
  assert.match(source,/useBookVisit/)
})
test('available access opens a choice instead of immediately navigating', () => {
  const source = readFileSync(new URL('../src/hooks/useBookVisit.ts', import.meta.url), 'utf8')
  assert.match(source, /result.decision === 'MEMBERSHIP'.*setChoiceOpen\(true\)/)
  assert.match(source, /else navigate\(visitDestination/)
})
test('membership popup has precisely two buttons and no close-button CTA', () => {
  const source = readFileSync(new URL('../src/components/membership/MembershipChoiceModal.tsx', import.meta.url), 'utf8')
  assert.equal((source.match(/<Button\b/g) || []).length, 2)
  assert.match(source, /showCloseButton=\{false\}/)
  assert.match(source, />Use My Membership<\/Button>/)
  assert.match(source, />Book for Others<\/Button>/)
  assert.doesNotMatch(source, /Cancel|View Membership/)
})
test('My Access is personal access only, with no companion or paid-booking links', () => {
  const source = readFileSync(new URL('../src/pages/access/ConfirmVisitPage.tsx', import.meta.url), 'utf8')
  assert.match(source, /Generate Visit QR/)
  assert.doesNotMatch(source, /Book for Others|friends|family|for=others|\/book\/|Add to Cart|Add People|purchase a visit/i)
})
test('companion flow reuses BookingPage and original cart services', () => {
  const wrapper = readFileSync(new URL('../src/pages/booking/CompanionBooking.tsx', import.meta.url),'utf8')
  const booking = readFileSync(new URL('../src/pages/booking/BookingPage.tsx', import.meta.url),'utf8')
  assert.match(wrapper, /<BookingPage gymId=\{gymId\} schedule companionsDate=/)
  assert.match(booking,/member_count: draft.memberCount/)
  assert.doesNotMatch(booking,/member_count:.*\+\s*1|fetch\(|\/api\/|price:\s*0|discount:/)
  assert.match(booking,/visitAccessService.check\(gymId\)/)
  assert.match(booking,/navigate\('\/cart'\)/)
})