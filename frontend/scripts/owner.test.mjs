import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

async function load(relative, transform = value => value) {
  const source = transform(readFileSync(new URL(relative, import.meta.url), 'utf8'))
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
}
const { ownerRoute, switchedGymPath } = await load('../src/owner/routes.ts')
const service = await load('../src/screens/GymOwner/api.ts', s => s.replace(/import .* from '..\/..\/services\/client'/, `const request = (...args) => globalThis.__ownerRequest(...args)`))
const owner = await load('../src/owner/services.ts', s => s.replace(/import .* from '..\/services\/client'/, `const request = (...args) => globalThis.__ownerRequest(...args); const post = (path, body) => globalThis.__ownerRequest(path, {method:'POST',body:JSON.stringify(body)})`))
const client = await load('../src/services/client.ts', s => s.replace(/import .* from '..\/auth'/, `const authFetch = (...args) => globalThis.__ownerFetch(...args); const clearTokens = () => {}; const getAccessToken = () => 'test';`))

for (const [path, page] of Object.entries({
  '/owner': 'dashboard', '/owner/dashboard': 'dashboard', '/owner/login': 'login', '/owner/register': 'register', '/owner/verify': 'verify',
  '/owner/gyms': 'gyms', '/owner/gyms/create': 'gymForm', '/owner/gyms/1': 'gym', '/owner/gyms/1/edit': 'gymForm',
  '/owner/gyms/1/memberships': 'memberships', '/owner/gyms/1/memberships/create': 'memberships', '/owner/gyms/1/memberships/2/edit': 'memberships',
  '/owner/gyms/1/classes': 'classes', '/owner/gyms/1/classes/create': 'classes', '/owner/gyms/1/classes/2/edit': 'classes', '/owner/gyms/1/slots': 'slots',
  '/owner/bookings': 'bookings', '/owner/bookings/1': 'bookingsDetail', '/owner/members': 'members', '/owner/members/1': 'membersDetail',
  '/owner/staff': 'staff', '/owner/staff/invite': 'staffForm', '/owner/staff/1': 'staffDetail', '/owner/check-in': 'check-in',
  '/owner/revenue': 'revenue', '/owner/analytics': 'analytics', '/owner/settings': 'settings', '/owner/notifications': 'notifications', '/owner/more': 'more'
})) test(`owner route ${path}`, () => assert.equal(ownerRoute(path).page, page))

test('owner routes reject invalid IDs and malformed paths', () => {
  for (const path of ['/owner/gyms/0', '/owner/gyms/9007199254740992', '/owner/gyms/-1', '/owner/gyms/1/slots/create', '/owner/gyms/1/edit/create', '/owner/gyms/1/classes/create/edit', '/owner/bookings/0', '/owner/random']) assert.equal(ownerRoute(path).page, 'notFound', path)
  assert.deepEqual(ownerRoute('/owner/gyms/4/classes/12/edit/'), { page: 'classes', gymId: 4, id: 12, mode: 'edit' })
})
test('switching gyms drops stale entity IDs and preserves module', () => {
  assert.equal(switchedGymPath('/owner/gyms/1/classes/99/edit', 2), '/owner/gyms/2/classes')
  assert.equal(switchedGymPath('/owner/gyms/1/memberships/create', 2), '/owner/gyms/2/memberships')
  assert.equal(switchedGymPath('/owner/gyms/1/edit', 2), '/owner/gyms/2')
  assert.equal(switchedGymPath('/owner/bookings/99', 2), '/owner/bookings')
  assert.equal(switchedGymPath('/owner/staff/99', 2), '/owner/staff')
  assert.equal(switchedGymPath('/owner/revenue', 2), '/owner/revenue')
})
test('booking actions fail closed without explicit server permissions', () => {
  for (const status of ['CONFIRMED', 'CANCELLED', 'PENDING_PAYMENT']) assert.deepEqual(owner.allowedBookingActions({ status }), [])
  assert.deepEqual(owner.allowedBookingActions({ allowed_actions: ['MARK_ATTENDED'] }), ['MARK_ATTENDED'])
})
test('booking pagination and selected gym are sent to real owner endpoint', async () => {
  let called
  globalThis.__ownerRequest = async (...args) => { called = args; return [] }
  await service.listBookings(7, { date: '2026-09-30', status: 'CONFIRMED', limit: 20, offset: 40 })
  assert.equal(called[0], '/gym-owner/gyms/7/bookings?date=2026-09-30&status=CONFIRMED&limit=20&offset=40')
})
test('selected gym is used by plans, staff, classes and public availability', async () => {
  const calls = []; globalThis.__ownerRequest = async (path) => { calls.push(path); return [] }
  await service.listOwnerSlots(42); await service.listOwnerMembershipPlans(42); await service.listStaff(42); await service.listPublicSlotAvailability(42, '2026-09-30')
  assert.deepEqual(calls, ['/gym-owner/gyms/42/slots', '/gym-owner/gyms/42/membership-plans', '/gym-owner/gyms/42/staff', '/gyms/42/slots?date=2026-09-30'])
})
test('QR validation passes the raw token and gym to the atomic backend endpoint', async () => {
  let called; globalThis.__ownerRequest = async (...args) => { called = args; return { success: false, status: 'QR_ALREADY_USED', message: 'Already used' } }
  const result = await owner.ownerService.checkIn(42, 'GYMACCESS:test-token')
  assert.equal(called[0], '/checkins/validate'); assert.deepEqual(JSON.parse(called[1].body), { gym_id: 42, qr_token: 'GYMACCESS:test-token' }); assert.equal(result.success, false)
})
test('upload uses FormData and shared client preserves browser multipart boundary', async () => {
  let called; globalThis.__ownerFetch = async (...args) => { called = args; return new Response('{}') }
  const body = new FormData(); body.append('file', new Blob(['test'], { type: 'image/png' }), 'test.png')
  await client.request('/gym-owner/gyms/1/images', { method: 'POST', body })
  assert.equal(called[1].headers.has('Content-Type'), false)
  assert.equal(called[1].body, body)
  await client.request('/gym-owner/gyms', { method: 'POST', body: JSON.stringify({ name: 'Test' }), headers: new Headers({ 'X-Test': 'yes' }) })
  assert.equal(called[1].headers.get('Content-Type'), 'application/json'); assert.equal(called[1].headers.get('X-Test'), 'yes')
})
test('all owner business APIs use the existing shared request client', () => {
  const source = readFileSync(new URL('../src/screens/GymOwner/api.ts', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /\bfetch\(|\bauthFetch\(|\bas any\b|\bas never\b/)
  assert.match(source, /services\/client/)
})
test('unsupported capabilities are explicit, never mocked business values', () => {
  for (const capability of Object.values(owner.capabilities)) { assert.equal(capability.available, false); assert.ok(capability.message.length > 20) }
})