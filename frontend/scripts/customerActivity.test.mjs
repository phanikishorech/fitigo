import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const read = path => readFileSync(new URL('../src/' + path, import.meta.url), 'utf8')
async function load(path, transform = source => source) {
  const code = ts.transpileModule(transform(read(path)), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
}
const routes = await load('customerRoutes.ts')
const { cartEditDraft } = await load('utils/cartEdit.ts')
const activity = await load('services/customerActivity.ts')
test('notifications and cart editing are protected customer routes and returnable', () => {
  for (const path of ['/notifications', '/cart/items/123/edit']) {
    assert.equal(routes.isProtectedRoute(routes.customerRoute(path)), true)
    assert.equal(routes.safeReturnTo(path), path)
  }
  assert.deepEqual(routes.customerRoute('/cart/items/123/edit'), { page: 'cartEdit', id: 123 })
  for (const path of ['/cart/items/0/edit', '/cart/items/-1/edit', '/cart/items/abc/edit', '/cart/items/9007199254740992/edit']) assert.equal(routes.customerRoute(path).page, 'notFound')
})
test('gym edit prefills actual date, count, times without changing ordinary draft', () => {
  const item = { gym_id: 4, booking_type: 'GYM', booking_date: '2027-01-03', member_count: 2, preferred_start_time: '14:15:00', preferred_end_time: '15:15:00', class_session_id: null }
  const draft = cartEditDraft(item)
  assert.deepEqual(draft, { gymId: 4, accessType: 'GYM', date: '2027-01-03', memberCount: 2, start: '14:15', end: '15:15', classId: null })
  draft.start = '16:00'; assert.equal(item.preferred_start_time, '14:15:00')
})
test('class edit retains selected session and server schedule', () => {
  const draft = cartEditDraft({ gym_id: 4, booking_type: 'CLASS', booking_date: '2027-01-03', member_count: 3, class_session_id: 12, start_time: '16:30:00', end_time: '17:30:00' })
  assert.equal(draft.classId, 12); assert.equal(draft.start, '16:30'); assert.equal(draft.accessType, 'CLASS')
  assert.throws(() => cartEditDraft({ booking_type: 'unknown' }))
})
test('visitor names survive remount in the existing in-memory draft without browser persistence', async () => {
  const draft = await load('store/bookingStore.ts', source => source
    .replace(/import \{ useSyncExternalStore \}[^\r\n]+/, 'const useSyncExternalStore=()=>{}')
    .replace(/import \{ localDate \}[^\r\n]+/, "const localDate=()=> '2026-11-12'"))
  draft.updateDraft(7, { visitorNames: ['Visitor One'], visitorOwnerId: 1, start: '09:00' })
  assert.deepEqual(draft.getDraft(7).visitorNames, ['Visitor One'])
  assert.deepEqual(draft.draftVisitors(draft.getDraft(7), 1), ['Visitor One'])
  assert.equal(draft.draftVisitors(draft.getDraft(7), 2), undefined)
  assert.equal(draft.getDraft(8).visitorNames, undefined)
  assert.equal(draft.getDraft(7, '2026-11-13').visitorNames, undefined)
  assert.doesNotMatch(read('store/bookingStore.ts'), /localStorage|sessionStorage/)
  assert.match(read('pages/booking/BookingPage.tsx'), /draftVisitors\(draft, user.id\)/)
})
test('successful cart mutation emits same-tab and cross-tab invalidation, failed mutation does not', async () => {
  globalThis.window = new EventTarget()
  const writes = []
  globalThis.localStorage = { setItem: (...args) => writes.push(args) }
  const events = [], off = activity.subscribeActivity(kind => events.push(kind))
  const result = await activity.cartMutation(Promise.resolve({ id: 1 }))
  assert.equal(result.id, 1); assert.deepEqual(events, ['cart']); assert.equal(writes.length, 1)
  assert.match(writes[0][1], /^cart:/)
  await assert.rejects(activity.cartMutation(Promise.reject(new Error('Rejected'))))
  assert.equal(writes.length, 1)
  const storage = new Event('storage'); storage.key = 'fitigo:customer-activity'; storage.newValue = 'notifications:1:0'
  window.dispatchEvent(storage); assert.deepEqual(events, ['cart', 'notifications'])
  off(); activity.notifyActivity('notifications'); assert.equal(events.length, 2)
})
test('storage restrictions do not turn successful mutations into failures', async () => {
  globalThis.window = new EventTarget(); globalThis.localStorage = { setItem: () => { throw Error('Disabled') } }
  assert.equal(await activity.cartMutation(Promise.resolve(7)), 7)
})
test('edit saves via PUT and never removes/recreates the cart item', async () => {
  const calls = []
  globalThis.__cartRequest = async (...args) => { calls.push(args); return { id: 8 } }
  const { bookingService } = await load('services/bookingService.ts', source => source
    .replace(/import \{ post, request \}[^\r\n]+/, 'const request=(...args)=>globalThis.__cartRequest(...args);const post=(path,body)=>request(path,{method:"POST",body:JSON.stringify(body)});')
    .replace(/import \{ cartMutation \}[^\r\n]+/, 'const cartMutation = promise => promise'))
  await bookingService.updateCart(8, { gym_id: 4, booking_type: 'GYM', booking_date: '2027-01-03', preferred_start_time: '14:00', member_count: 1, visitor_names: ['Updated visitor'], expected_updated_at: '2026-11-12T12:00:00' })
  assert.equal(calls.length, 1); assert.equal(calls[0][0], '/cart/items/8'); assert.equal(calls[0][1].method, 'PUT')
  assert.deepEqual(JSON.parse(calls[0][1].body).visitor_names, ['Updated visitor'])
  assert.ok(JSON.parse(calls[0][1].body).expected_updated_at)
})
test('inbox moves out of settings and header uses real authenticated counts', () => {
  assert.match(read('pages/profile/SettingsPage.tsx'), /NotificationCenter inbox=\{false\}/)
  assert.match(read('pages/profile/NotificationsPage.tsx'), /NotificationCenter preferences=\{false\}/)
  const header = read('components/navigation/CustomerActivity.tsx')
  assert.match(header, /name="bell"/); assert.match(header, /\/cart\/summary/); assert.match(header, /unread_count/)
  assert.match(header, /if \(userId === null\) return/)
  assert.doesNotMatch(read('components/navigation/customerActivity.css'), /font-family|--fg-green\s*:/)
})