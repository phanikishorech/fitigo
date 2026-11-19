import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

async function load(file, transform = source => source) {
  const compiled = ts.transpileModule(transform(readFileSync(new URL(file, import.meta.url), 'utf8')), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(compiled + `\n// ${Math.random()}`).toString('base64')}`)
}
const geo = await load('../src/maps/geo.ts')
test('gym details exposes only a sidebar directions link before booking, without an embedded map', () => {
  const source = readFileSync(new URL('../src/pages/discovery/GymPage.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /GymDirections|MapCanvas|Suspense|requestPosition|useLocation/)
  const sidebar = source.slice(source.indexOf('<aside'), source.indexOf('</aside>'))
  assert.match(sidebar, /href=\{directionsUrl\(destination, 'DRIVING'\)\}/)
  assert.ok(sidebar.indexOf('Get Directions') > sidebar.indexOf('gym.opening_hours.open_today'))
  assert.ok(sidebar.indexOf('Get Directions') < sidebar.indexOf('Your workout, your way'))
  assert.match(sidebar, /Book a Visit/)
  assert.match(sidebar, /View Membership Plans/)
  assert.match(sidebar, /Location unavailable/)
})
test('coordinate validation rejects missing, invalid and nonfinite values, preserves zero', () => {
  for (const values of [[null, 0], ['', 0], [' ', 0], [NaN, 1], [Infinity, 0], [91, 0], [0, -181]]) assert.equal(geo.point(...values), null)
  assert.deepEqual(geo.point('0', '0'), { lat: 0, lng: 0 })
  assert.deepEqual(geo.point('-90', '180'), { lat: -90, lng: 180 })
})
test('directions URLs support every travel mode and omit denied origin', () => {
  for (const mode of ['DRIVING', 'WALKING', 'BICYCLING', 'TRANSIT']) {
    const url = new URL(geo.directionsUrl({ lat: 12, lng: 77 }, mode))
    assert.equal(url.origin, 'https://www.google.com'); assert.equal(url.searchParams.get('api'), '1')
    assert.equal(url.searchParams.get('destination'), '12,77'); assert.equal(url.searchParams.get('travelmode'), mode.toLowerCase())
    assert.equal(url.searchParams.has('origin'), false)
  }
  assert.equal(new URL(geo.directionsUrl({ lat: 12, lng: 77 }, 'DRIVING', { lat: 0, lng: 0 })).searchParams.get('origin'), '0,0')
})
test('clusters expand at high zoom without dropping colocated gyms', () => {
  const pins = [{ lat: 1, lng: 1, id: 1 }, { lat: 1, lng: 1, id: 2 }, { lat: -20, lng: 90, id: 3 }]
  assert.equal(geo.clusterPoints(pins, 5).length, 2)
  assert.equal(geo.clusterPoints(pins, 19).length, 3)
})
async function locationModule({ code, unsupported = false, permission = 'prompt' } = {}) {
  let count = 0, handler
  const status = { state: permission, addEventListener: (name, callback) => { handler = callback } }
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: {
    permissions: { query: async () => status },
    geolocation: unsupported ? undefined : { getCurrentPosition: (success, fail) => { count++; queueMicrotask(() => code ? fail({ code }) : success({ coords: { latitude: 12, longitude: 77, accuracy: 30 }, timestamp: Date.now() })) } }
  } })
  globalThis.window = { isSecureContext: true }
  globalThis.__forgot = 0
  const module = await load('../src/maps/location.ts', source => source.replace(/import \{ forgetCurrentLocation \}[^\n]+/, 'const forgetCurrentLocation = () => globalThis.__forgot++'))
  return { module, count: () => count, revoke: () => { status.state = 'denied'; handler() } }
}
test('granted geolocation is deduplicated and memory-only; revocation clears position', async () => {
  const fixture = await locationModule()
  const [one, two] = await Promise.all([fixture.module.requestPosition(true), fixture.module.requestPosition(true)])
  assert.deepEqual(one, two); assert.equal(fixture.count(), 1); assert.equal(one.accuracy, 30)
  fixture.revoke(); assert.equal(fixture.module.locationSnapshot().position, null); assert.ok(globalThis.__forgot)
  assert.equal(await fixture.module.requestPosition(), null); assert.equal(fixture.count(), 1)
})
for (const [code, expected] of [[1, /denied/], [2, /unavailable/], [3, /timed out/]]) test(`geolocation error ${code} never blocks manual discovery or repeatedly prompts`, async () => {
  const fixture = await locationModule({ code })
  assert.equal(await fixture.module.requestPosition(true), null)
  assert.match(fixture.module.locationSnapshot().error, expected)
  await fixture.module.requestPosition(true); assert.equal(fixture.count(), 1)
})
test('unsupported and already-denied browsers never request geolocation', async () => {
  for (const options of [{ unsupported: true }, { permission: 'denied' }]) {
    const fixture = await locationModule(options); assert.equal(await fixture.module.requestPosition(), null); assert.equal(fixture.count(), 0)
  }
})
test('manual areas persist; precise browser coordinates do not; legacy data is removed', async () => {
  const storage = new Map()
  globalThis.localStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) }
  const makeStore = () => load('../src/screens/NearbyGyms/LocationStore.ts', source => source.replace(/import \{ point \}[^\n]+/, `const point = ${geo.point.toString()}`))
  const store = await makeStore()
  store.setStoredLocation({ location_name: 'Fixture area', latitude: 1, longitude: 2 })
  store.setStoredLocation({ location_name: 'Current location', source: 'current', latitude: 12.345, longitude: 77.654 })
  assert.equal(JSON.parse(storage.get('fitigo.location')).location_name, 'Fixture area')
  store.forgetCurrentLocation(); assert.equal(store.getStoredLocation().location_name, 'Fixture area')
  storage.set('fitigo.location', JSON.stringify({ location_name: 'Current location', latitude: 12, longitude: 77 }))
  assert.equal((await makeStore()).getStoredLocation(), null); assert.equal(storage.size, 0)
})
test('map styles reuse design tokens and cannot redefine typography or theme', () => {
  const css = readFileSync(new URL('../src/maps/maps.css', import.meta.url), 'utf8')
  assert.doesNotMatch(css, /font-family|@import|--fg-green\s*:|:root/)
  assert.match(css, /var\(--fg-green\)/); assert.match(css, /var\(--fg-border\)/)
})