import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

async function load(relative, transform = value => value) {
  const source = transform(readFileSync(new URL(relative, import.meta.url), 'utf8'))
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
}
const { customerRoute, isProtectedRoute, safeReturnTo } = await load('../src/customerRoutes.ts')
const { amountInMinorUnits, canReview, isBookableSession } = await load('../src/utils/booking.ts')
const client = await load('../src/services/client.ts', source => source.replace(/import .* from '..\/auth'/, `
  const authFetch = (...args) => globalThis.__fitigoFetch(...args);
  const getAccessToken = () => globalThis.__fitigoToken;
  const clearTokens = () => { globalThis.__fitigoToken = null };
`))

for (const [path, expected] of Object.entries({
  '/': 'home', '/home': 'home', '/explore': 'explore', '/explore/search': 'explore', '/nearby': 'explore',
  '/location': 'location', '/gyms/188': 'gym', '/gyms/188/access': 'bookingAccess', '/gyms/188/book/access': 'bookingAccess',
  '/gyms/188/book/schedule': 'bookingSchedule', '/gyms/188/membership': 'plans', '/cart': 'cart', '/checkout': 'checkout',
  '/wallet': 'wallet', '/wallet/recharge': 'recharge', '/bookings': 'bookings', '/bookings/42': 'bookingDetail',
  '/booking/42': 'bookingDetail', '/booking/42/success': 'bookingSuccess', '/membership': 'membership',
  '/membership/checkout': 'membershipCheckout', '/membership/success': 'membershipSuccess', '/profile': 'profile',
  '/profile/membership': 'membership', '/profile/access': 'calendar', '/profile/access/today': 'access', '/access/qr': 'access',
  '/profile/history': 'history', '/profile/visits': 'visits', '/reviews/42': 'review', '/staff/check-in': 'staff',
  '/auth': 'auth', '/auth/login': 'auth', '/auth/otp': 'auth', '/auth/profile-setup': 'settings', '/does-not-exist': 'notFound'
})) test(`route: ${path}`, () => assert.equal(customerRoute(path).page, expected))

test('routes tolerate trailing slash and reject invalid identifiers', () => {
  assert.deepEqual(customerRoute('/gyms/188/'), { page: 'gym', id: 188 })
  for (const path of ['/gyms/0', '/gyms/-1', '/gyms/NaN', '/gyms/9007199254740992']) assert.equal(customerRoute(path).page, 'notFound')
})
test('customer data and mutations are protected; browsing remains public', () => {
  for (const path of ['/wallet', '/cart', '/checkout', '/membership/checkout', '/profile', '/access/qr', '/reviews/1']) assert.equal(isProtectedRoute(customerRoute(path)), true)
  for (const path of ['/home', '/explore', '/gyms/1', '/gyms/1/book/schedule', '/gyms/1/membership']) assert.equal(isProtectedRoute(customerRoute(path)), false)
})
test('post-login intent is preserved without open redirects', () => {
  const intent = '/membership/checkout?gymId=188&planId=3'
  assert.equal(safeReturnTo(intent), intent)
  assert.equal(safeReturnTo('/gyms/188/book/schedule'), '/gyms/188/book/schedule')
  for (const value of ['https://evil.test', '//evil.test', '/\\evil.test', '/auth/login', '/unknown', null]) assert.equal(safeReturnTo(value), '/home')
})
test('class status uses real backend enum, not invented ACTIVE status', () => {
  assert.equal(isBookableSession('AVAILABLE', 5), true)
  assert.equal(isBookableSession('FEW_SLOTS_LEFT', 1), true)
  for (const status of ['CANCELLED', 'CLOSED', 'FULL', 'ACTIVE']) assert.equal(isBookableSession(status, 10), false)
  assert.equal(isBookableSession('AVAILABLE', 0), false)
})
test('wallet comparisons use minor units', () => {
  assert.equal(amountInMinorUnits('0.10') + amountInMinorUnits('0.20'), 30)
  assert.equal(amountInMinorUnits('1250.99'), 125099)
  for (const value of ['invalid', -1, Infinity]) assert.throws(() => amountInMinorUnits(value))
})
test('only attended real bookings can submit a review', () => {
  assert.equal(canReview({ booking_id: 1, booking_status: 'COMPLETED', attendance_status: 'ATTENDED' }), true)
  assert.equal(canReview({ booking_id: 1, booking_status: 'CONFIRMED', attendance_status: null }), false)
  assert.equal(canReview({ booking_id: -3, booking_status: 'COMPLETED', attendance_status: 'ATTENDED' }), false)
  assert.equal(canReview({ booking_id: 1, booking_status: 'CANCELLED', attendance_status: 'ATTENDED' }), false)
})
test('API errors do not leak internal diagnostics', () => {
  assert.equal(client.safeError(409, 'You already have an active membership for this gym.'), 'You already have an active membership for this gym.')
  assert.ok(!client.safeError(500, 'SQL traceback secret').includes('SQL'))
  assert.ok(!client.safeError(400, '<html>internal</html>').includes('<html>'))
  assert.match(client.safeError(401), /sign in/i)
  assert.match(client.safeError(422, [{ msg: 'bad input' }]), /check your selections/i)
})
test('missing token never reaches legacy development-account endpoints', async () => {
  globalThis.__fitigoToken = null
  globalThis.__fitigoFetch = () => { throw new Error('must not call backend') }
  await assert.rejects(client.request('/wallet/balance'), error => error.status === 401)
})
test('expired token cannot fall back to the development account', async () => {
  globalThis.__fitigoToken = 'expired-test-token'
  const calls = []
  globalThis.__fitigoFetch = async path => { calls.push(path); return new Response('{}', { status: 401 }) }
  await assert.rejects(client.request('/cart/items'), error => error.status === 401)
  assert.deepEqual(calls, ['/api/v1/users/me'])
  assert.equal(globalThis.__fitigoToken, null)
})
test('valid customer session forwards real requests after identity verification', async () => {
  globalThis.__fitigoToken = 'unit-test-token'
  const calls = []
  globalThis.__fitigoFetch = async (path, init) => { calls.push({ path, init }); return new Response(JSON.stringify(path.endsWith('/users/me') ? { id: 1 } : { balance: '250.00', currency: 'INR' })) }
  assert.equal((await client.request('/wallet/balance')).balance, '250.00')
  assert.deepEqual(calls.map(call => call.path), ['/api/v1/users/me', '/api/v1/wallet/balance'])
})
test('public browsing does not require authentication', async () => {
  globalThis.__fitigoToken = null
  globalThis.__fitigoFetch = async path => { assert.equal(path, '/api/v1/gyms/discover'); return new Response('{"gyms":[]}') }
  assert.deepEqual(await client.request('/gyms/discover'), { gyms: [] })
})
test('network failures have a useful retry message', async () => {
  globalThis.__fitigoFetch = async () => { throw new TypeError('Failed to fetch') }
  await assert.rejects(client.request('/gyms/discover'), /Check your internet connection/)
})
test('invalid JSON is an error, not an empty success', async () => {
  globalThis.__fitigoFetch = async () => new Response('<html>broken proxy</html>')
  await assert.rejects(client.request('/gyms/discover'), /unexpected response/)
})

const { cachedRead, clearReadCache } = await load('../src/services/readCache.ts')
test('read cache deduplicates in-flight gym reads', async () => {
  clearReadCache()
  let calls = 0
  const loadGym = async () => { calls++; return { id: 188 } }
  const [first, second] = await Promise.all([cachedRead('gym:188', loadGym), cachedRead('gym:188', loadGym)])
  assert.equal(calls, 1)
  assert.deepEqual(first, second)
})
test('failed reads are evicted so retry works', async () => {
  clearReadCache()
  await assert.rejects(cachedRead('gym:1', async () => { throw new Error('network') }))
  assert.equal(await cachedRead('gym:1', async () => 'recovered'), 'recovered')
})
test('cache clearing forces fresh data on session change', async () => {
  await cachedRead('membership-gym', async () => 'old')
  clearReadCache()
  assert.equal(await cachedRead('membership-gym', async () => 'new'), 'new')
})