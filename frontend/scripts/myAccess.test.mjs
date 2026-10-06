import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const compile = source => `data:text/javascript;base64,${Buffer.from(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText).toString('base64')}`
const utils = await import(compile(read('../src/utils/membership.ts')))
globalThis.__myAccessUtils = utils
const source = read('../src/services/myAccessService.ts')
  .replace(/import .* from '.\/accountService'/, 'const {accessService,membershipService,profileService}=globalThis.__myAccessMocks')
  .replace(/import .* from '.\/gymService'/, 'const {gymService}=globalThis.__myAccessMocks')
  .replace(/import .* from '.\/membershipPauseService'/, 'const {membershipPauseService}=globalThis.__myAccessMocks')
  .replace(/import .* from '..\/utils\/membership'/, 'const {dayPresentation,todayFrom}=globalThis.__myAccessUtils')
let calendar, summary, memberships, failure, calls
globalThis.__myAccessMocks = {
  accessService: { current: async () => { if (failure) throw failure; return calendar } },
  membershipService: { summary: async () => summary, mine: async () => memberships },
  profileService: { me: async () => ({ first_name: 'Test', last_name: 'Member' }) },
  gymService: { accessDetails: async id => { calls.push(['gym', id]); return { gym_id: id, gym_name: 'Backend assigned gym' } } },
  membershipPauseService: { eligibility: async id => { calls.push(['pause', id]); return { currently_paused: true, current_pause: { end_date: '2026-10-10', resumes_on: '2026-10-11' } } } },
}
const { myAccessService, validateAccessCalendar } = await import(compile(source))
function reset(type = 'MULTI_GYM', status = 'ACTIVE') {
  calls = []; failure = null
  calendar = { access_type: type, gym: type === 'SINGLE_GYM' ? { id: 42, name: 'Backend assigned gym' } : null, days: [{ date: '2026-10-06', status: 'TODAY', qr_status: status, qr_available: status === 'ACTIVE' }] }
  summary = { membership_id: 7, membership_scope: type, status: 'ACTIVE', plan_name: 'Deliberately misleading Single-Gym name' }
  memberships = [{ id: 7, gym_id: type === 'SINGLE_GYM' ? 42 : null }]
}
test('direct Multi-Gym uses backend scope and requires no gym selection or QR issuance', async () => {
  reset(); const result = await myAccessService.current()
  assert.equal(result.type, 'MULTI_GYM'); assert.equal(result.gym, null); assert.deepEqual(calls, [])
  assert.equal(result.customer.first_name, 'Test')
})
test('Single-Gym loads the assigned backend gym without searching', async () => {
  reset('SINGLE_GYM'); const result = await myAccessService.current()
  assert.equal(result.gym.gym_id, 42); assert.deepEqual(calls, [['gym', 42]])
})
test('paused membership uses existing pause dates, not client date calculations', async () => {
  reset('SINGLE_GYM', 'PAUSED'); calendar.access_type = null; calendar.gym = null
  const result = await myAccessService.current()
  assert.equal(result.type, 'SINGLE_GYM'); assert.equal(result.pause.current_pause.end_date, '2026-10-10')
  assert.deepEqual(calls, [['gym', 42], ['pause', 7]])
})
test('used, paused, expired and inactive contracts remain non-generating', async () => {
  for (const status of ['USED', 'PAUSED', 'EXPIRED', 'NO_ACCESS', 'REVOKED']) {
    reset('MULTI_GYM', status)
    assert.equal(utils.hasAvailableAccess((await myAccessService.current()).calendar), false)
  }
})
test('network failures and malformed/unknown availability remain errors', async () => {
  reset(); failure = new Error('Network unavailable')
  await assert.rejects(myAccessService.current(), /Network unavailable/)
  for (const change of [c => c.days = [], c => c.days[0].qr_status = 'UNKNOWN', c => c.days[0].qr_available = false, c => c.access_type = null, c => { c.access_type = 'SINGLE_GYM'; c.gym = null }]) {
    reset(); change(calendar); assert.throws(() => validateAccessCalendar(calendar))
  }
})
test('My Access and QR remain personal-only and generation is explicitly locked', () => {
  const page = read('../src/pages/access/AccessPage.tsx'), card = read('../src/components/membership/MyAccessCard.tsx'), hook = read('../src/hooks/useAccessQr.ts')
  assert.match(page, /navigate\('\/access\/qr\?generate=1'\)/)
  assert.match(page, /if \(lock.current\) return/); assert.match(hook, /if \(lock.current\) return/)
  assert.match(card, /available && type === 'MULTI_GYM'/)
  assert.match(hook, /accessService.today\(\)/)
  assert.doesNotMatch(page + card, /Book for Others|Guest Booking|Add to Cart|for=others|\/book\//i)
  assert.doesNotMatch(source, /setDate\(|getDate\(|86400000|fetch\(/)
})