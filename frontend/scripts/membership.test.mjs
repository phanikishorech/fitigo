import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
async function load(path, transform = value => value) {
  const source = transform(readFileSync(new URL(path, import.meta.url), 'utf8'))
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
}
const routes = await load('../src/customerRoutes.ts')
const state = await load('../src/utils/membership.ts')
const client = await load('../src/services/client.ts', source => source.replace(/import .* from '..\/auth'/, `const authFetch=(...args)=>globalThis.__membershipFetch(...args);const getAccessToken=()=>globalThis.__membershipToken;const clearTokens=()=>{globalThis.__membershipToken=null};`))
const account = await load('../src/services/accountService.ts', source => source.replace(/import .* from '.\/client'/, `const request=(...args)=>globalThis.__membershipRequest(...args);const post=()=>{throw new Error('Unexpected mutation')}`))

test('membership choices depend on backend status, not record existence or dates', () => {
  assert.equal(state.membershipOverviewState([], null), 'none')
  for (const status of ['NONE', 'EXPIRED', 'INACTIVE', 'CANCELLED', 'PAUSED']) {
    assert.equal(state.membershipOverviewState([{ status }], status), 'none')
  }
  assert.equal(state.membershipOverviewState([{status:'EXPIRED'}, {status:'ACTIVE'}], 'ACTIVE'), 'active')
  assert.equal(state.membershipOverviewState([{status:'ACTIVE',end_at:'2000-01-01'}], null), 'active')
  assert.equal(state.membershipOverviewState([], 'ACTIVE'), 'active')
  assert.equal(state.membershipOverviewState([{status:'PENDING'}], 'PENDING'), 'unknown')
  assert.equal(state.membershipOverviewState([], 'NEW_STATUS'), 'unknown')
})
test('Multi-Gym plan destination is recognized and session protected', () => {
  const route = routes.customerRoute('/membership/multi-gym/plans')
  assert.equal(route.page, 'multiGymPlans')
  assert.equal(routes.isProtectedRoute(route), true)
})

for (const [path, page] of Object.entries({ '/membership/42': 'membershipRecord', '/membership/42/details': 'membershipDetails', '/membership/pause': 'membershipPause', '/membership/gyms': 'membershipGyms', '/gyms': 'membershipGyms', '/gyms/12/visit': 'confirmVisit' })) test(`protected membership route ${path}`, () => { assert.equal(routes.customerRoute(path).page, page); assert.equal(routes.isProtectedRoute(routes.customerRoute(path)), true) })
test('membership IDs and return paths are validated', () => {
  for (const path of ['/membership/0', '/membership/-1', '/membership/9007199254740992', '/gyms/0/visit', '/membership/1/details/pause']) assert.equal(routes.customerRoute(path).page,'notFound')
  assert.equal(routes.safeReturnTo('/gyms/12/visit'),'/gyms/12/visit')
})
test('visited, consumed and paused days remain distinct', () => {
  assert.equal(state.dayPresentation({ status: 'VISITED', qr_status: 'USED' }), 'VISITED')
  assert.equal(state.dayPresentation({ status: 'NO_VISIT', qr_status: 'EXPIRED' }), 'CONSUMED')
  assert.equal(state.dayPresentation({ status: 'PAUSED', qr_status: 'PAUSED' }), 'PAUSED')
  assert.equal(state.dayPresentation({ status: 'TODAY', qr_status: 'USED', checkin_time: '08:15:00' }), 'VISITED')
  assert.equal(state.dayPresentation({ status: 'TODAY', qr_status: 'USED', checkin_time: null }), 'USED')
})
test('unknown, past or future dates never imply availability', () => {
  assert.equal(state.dayPresentation({ status: 'FUTURE', qr_available: false }), 'FUTURE')
  assert.equal(state.dayPresentation({ status: 'NONE', qr_available: false }), 'NONE')
  assert.equal(state.dayPresentation({ status: 'NEW_STATE', qr_available: false }), 'UNAVAILABLE')
  assert.equal(state.dayPresentation({ status: 'TODAY', qr_status: 'ACTIVE', qr_available: false }), 'UNAVAILABLE')
  assert.equal(state.dayPresentation({ status: 'TODAY', qr_status: 'ACTIVE', qr_available: true }), 'AVAILABLE')
})
test('current access uses explicit TODAY and backend flags only', () => {
  const date = { status: 'TODAY', date: '2026-10-01', qr_status: 'ACTIVE', qr_available: true }
  assert.equal(state.hasAvailableAccess({ days: [date] }), true)
  for (const qr_status of ['USED','PAUSED','EXPIRED','NO_ACCESS']) assert.equal(state.hasAvailableAccess({ days: [{ ...date, qr_status }] }), false)
  assert.equal(state.hasAvailableAccess({ days: [{ ...date, status: 'FUTURE' }] }), false)
})
test('UTC timestamps do not silently become local time', () => {
  assert.equal(state.utcTimestamp('2026-10-01T08:15:00'), '2026-10-01T08:15:00Z')
  assert.equal(state.utcTimestamp('2026-10-01T08:15:00+00:00'), '2026-10-01T08:15:00+00:00')
  assert.match(state.membershipDate('2026-10-01T23:59:59Z'), /01.*Oct.*2026/)
})
test('read-only access status never calls credential-minting endpoint', async () => {
  const calls = []; globalThis.__membershipRequest = async (...args) => { calls.push(args); return { days: [] } }
  await account.accessService.current()
  assert.equal(calls.length,1); assert.match(calls[0][0], /^\/customer\/access-calendar\?year=\d+&month=\d+$/)
  assert.equal(calls[0][1].cache,'no-store')
})
test('QR issuance uses existing backend endpoint and no invented gym payload', async () => {
  let call; globalThis.__membershipRequest = async (...args) => { call = args; return { status: 'PAUSED' } }
  assert.deepEqual(await account.accessService.today(), { status: 'PAUSED' }); assert.equal(call[0],'/customer/access/today'); assert.equal(call[1].cache,'no-store')
})
for (const code of Object.keys(client.accessErrorMessages)) test(`safe business error ${code}`, async () => {
  globalThis.__membershipToken = 'test'; globalThis.__membershipFetch = async () => new Response(JSON.stringify({ detail: { code, message: 'SQL private error' } }), { status: 403 })
  await assert.rejects(client.request('/test'), error => error.code === code && error.message === client.accessErrorMessages[code] && !error.message.includes('SQL'))
})
test('unknown business errors cannot leak raw structured details', async () => {
  globalThis.__membershipFetch = async () => new Response(JSON.stringify({ detail: { code: 'UNKNOWN', message: 'SQL private error' } }), { status: 400 })
  await assert.rejects(client.request('/test'), error => !error.code && !error.message.includes('SQL'))
})
test('server errors cannot masquerade as known access states', async () => {
  globalThis.__membershipFetch = async () => new Response(JSON.stringify({ code: 'MEMBERSHIP_PAUSED' }), { status: 500 })
  await assert.rejects(client.request('/test'), error => !error.code && /Something went wrong/.test(error.message))
})
test('pause is explicitly unavailable; no invented submission or expiry arithmetic', () => {
  const source = readFileSync(new URL('../src/components/membership/MembershipUI.tsx', import.meta.url),'utf8')
  assert.match(source,/Pause scheduling is not available/)
  assert.doesNotMatch(source,/\/api\/|new_expiry|pause_days_remaining/)
})