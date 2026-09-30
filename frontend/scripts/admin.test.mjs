import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

async function load(relative, transform = source => source) {
  const source = transform(readFileSync(new URL(relative, import.meta.url), 'utf8'))
  const result = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(result).toString('base64')}`)
}
const { adminRoute, adminReturnTo } = await load('../src/admin/routes.ts')
const service = await load('../src/screens/Admin/api.ts', source => source.replace(/import .* from '..\/..\/services\/client'/, `const request=(...args)=>globalThis.__adminRequest(...args);const post=(path,body)=>request(path,{method:'POST',body:JSON.stringify(body)})`))
for (const [path, page] of Object.entries({ '/admin': 'dashboard', '/admin/dashboard': 'dashboard', '/admin/login': 'login', '/admin/users': 'users', '/admin/users/1': 'user', '/admin/gyms': 'gyms', '/admin/gyms/2': 'gym', '/admin/gyms/2/review': 'review', '/admin/bookings': 'bookings', '/admin/bookings/3': 'booking', '/admin/reports': 'reports', '/admin/profile': 'profile', '/admin/notifications': 'notifications', '/admin/access-denied': 'access-denied', '/admin/session-expired': 'session-expired' })) test(`admin route ${path}`, () => assert.equal(adminRoute(path).page, page))
test('admin routing rejects malformed IDs and invalid review routes', () => {
  for (const path of ['/admin/gyms/0', '/admin/users/-1', '/admin/bookings/9007199254740992', '/admin/users/1/review', '/admin/not-real', '/admin/bookings/FG123']) assert.equal(adminRoute(path).page, 'notFound')
  assert.deepEqual(adminRoute('/admin/gyms/42/review/'), { page: 'review', id: 42 })
})
test('return-to cannot redirect outside protected admin routes', () => {
  for (const value of [null, '//evil.test', 'https://evil.test', '/owner', '/admin/login', '/admin/unknown']) assert.equal(adminReturnTo(value), '/admin/dashboard')
  assert.equal(adminReturnTo('/admin/gyms?status=PENDING_APPROVAL'), '/admin/gyms?status=PENDING_APPROVAL')
})
test('query encoding preserves false and zero, excludes only missing values', () => {
  assert.equal(service.query({ q: 'A & B', is_active: false, offset: 0, status: '', role: undefined }), '?q=A+%26+B&is_active=false&offset=0')
})
test('lists use real server-side filters and pagination', async () => {
  const calls = []; globalThis.__adminRequest = async (...args) => { calls.push(args); return [] }
  await service.fetchAdminUsers({ q: 'Jo', role: 'ADMIN', limit: 20, offset: 40 })
  await service.fetchAdminGyms({ status: 'PENDING_APPROVAL', limit: 21, offset: 20 })
  await service.fetchAdminBookings({ payment_status: 'PAID', date: '2026-09-30', gym_id: 2, limit: 21, offset: 20 })
  assert.equal(calls[0][0], '/admin/users?q=Jo&role=ADMIN&limit=20&offset=40')
  assert.equal(calls[1][0], '/admin/gyms?status=PENDING_APPROVAL&limit=21&offset=20')
  assert.equal(calls[2][0], '/admin/bookings?payment_status=PAID&date=2026-09-30&gym_id=2&limit=21&offset=20')
})
test('force cancellation sends reason only, never a fabricated refund state', async () => {
  let call; globalThis.__adminRequest = async (...args) => { call = args; return { new_status: 'CANCELLED' } }
  const result = await service.adminCancelBooking(42, '  Administrative request  ')
  assert.equal(call[0], '/admin/bookings/42/cancel'); assert.equal(call[1].method, 'POST')
  assert.deepEqual(JSON.parse(call[1].body), { reason: 'Administrative request' }); assert.equal(result.new_status, 'CANCELLED')
})
test('approval and rejection use confirmed mutation contracts', async () => {
  const calls = []; globalThis.__adminRequest = async (...args) => { calls.push(args); return { new_status: 'APPROVED' } }
  await service.adminApproveGym(8); await service.adminRejectGym(8, 'Missing information'); await service.adminUpdateUserStatus(3, { status: 'INACTIVE' })
  assert.equal(calls[0][0], '/admin/gyms/8/approve'); assert.equal(calls[1][0], '/admin/gyms/8/reject')
  assert.deepEqual(JSON.parse(calls[1][1].body), { reason: 'Missing information' })
  assert.equal(calls[2][0], '/admin/users/3/status')
})
test('all admin API transport reuses shared client, no raw fetch', () => {
  const source = readFileSync(new URL('../src/screens/Admin/api.ts', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /\bfetch\(|\bauthFetch\(|\bas any\b/)
})
test('dashboard labels do not misrepresent backend metrics', () => {
  const source = readFileSync(new URL('../src/admin/Dashboard.tsx', import.meta.url), 'utf8')
  assert.match(source, /Total gyms/); assert.match(source, /Revenue · last 30 days/)
  assert.doesNotMatch(source, /Today's revenue|title="Active gyms"/)
})
test('gym review does not bypass ownership or invent a detail endpoint', () => {
  const source = readFileSync(new URL('../src/admin/services.ts', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /\/gym-owner\/|request.*\/admin\/gyms\/\$\{id\}/)
  assert.match(source, /signal\?\.aborted/)
})