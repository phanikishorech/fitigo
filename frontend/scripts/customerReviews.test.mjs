import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
async function load(path, transform = s => s) {
  const code = ts.transpileModule(transform(read(path)), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
}
const { canReview } = await load('../src/utils/booking.ts')
const { reviewService } = await load('../src/services/accountService.ts', s => s.replace(/import \{ post, request \}[^\r\n]+/, 'const request=(...args)=>globalThis.__reviewRequest(...args);const post=(url,body)=>request(url,{method:"POST",body:JSON.stringify(body)});'))
const { bookingService } = await load('../src/services/bookingService.ts', s => s.replace(/import \{ post, request \}[^\r\n]+/, 'const request=(...args)=>globalThis.__reviewRequest(...args);const post=(url,body)=>request(url,{method:"POST",body:JSON.stringify(body)});'))
test('review eligibility cannot be inferred from manual attended flags', () => {
  const visit = { booking_id: 1, booking_status: 'COMPLETED', attendance_status: 'ATTENDED' }
  assert.equal(canReview(visit), false)
  assert.equal(canReview({ ...visit, can_review: true }), true)
  assert.equal(canReview({ ...visit, can_review: true, membership_covered: true }), false)
  assert.equal(canReview({ ...visit, can_review: true, booking_status: 'CANCELLED' }), false)
})
test('review APIs bind eligibility and submission to the selected booking', async () => {
  const calls = []; globalThis.__reviewRequest = async (...args) => { calls.push(args); return {} }
  await reviewService.eligibility(17)
  await reviewService.submit(2, 4, ' Good gym ', 17)
  assert.equal(calls[0][0], '/profile/bookings/17/review')
  assert.deepEqual(JSON.parse(calls[1][1].body), { rating: 4, comment: 'Good gym', booking_id: 17 })
  await bookingService.visits('all')
  assert.equal(calls[2][0], '/profile/bookings?status=all&source=individual')
})
test('profile has one membership-only history link and individual My bookings', () => {
  const profile = read('../src/pages/profile/ProfilePage.tsx')
  assert.match(profile, /My bookings/); assert.match(profile, /Membership visit history/)
  assert.match(profile, /has_membership_history/)
  assert.doesNotMatch(profile, /Check-in history|Upcoming visits/)
  const history = read('../src/pages/access/MembershipVisitHistory.tsx')
  assert.match(history, /\/profile\/membership-visits/)
  assert.match(history, /offset=/)
})
test('rating form supports existing feedback and does not override moderation', () => {
  const form = read('../src/pages/reviews/ReviewPage.tsx')
  assert.match(form, /visit.review\?\.rating/); assert.match(form, /visit.review\?\.comment/)
  assert.match(form, /clearReadCache/); assert.match(form, /hidden by moderation/)
  assert.match(form, /aria-pressed/); assert.match(form, /disabled=\{!rating\}/)
})