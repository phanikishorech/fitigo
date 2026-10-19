import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

async function load(path, transform = s => s) {
  const source = transform(readFileSync(new URL(path, import.meta.url), 'utf8'))
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
}
const booking = await load('../src/utils/booking.ts')
const display = await load('../src/utils/membership.ts')
const account = await load('../src/services/accountService.ts', s => s.replace(/import .* from '.\/client'/, 'const request=(...args)=>globalThis.__istRequest(...args); const post=()=>{};'))

test('IST date and selected time are independent of browser timezone', () => {
  const previous = process.env.TZ
  try {
    for (const zone of ['UTC', 'Asia/Kolkata', 'America/Los_Angeles', 'Pacific/Auckland']) {
      process.env.TZ = zone
      const now = Date.parse('2026-10-31T18:30:00Z')
      assert.equal(booking.istDateKey(now), '2026-11-01')
      assert.equal(booking.isFutureBookingStart('2026-11-01', '00:00', now), false)
      assert.equal(booking.isFutureBookingStart('2026-11-01', '00:15', now), true)
      assert.match(display.istDateTime('2026-10-31T18:30:00Z'), /01.*Nov.*2026/)
      assert.match(display.istDateTime('2026-10-31T18:30:00Z'), /IST$/)
      assert.equal(display.membershipTime('2026-11-01T18:15:00+05:30'), display.membershipTime('2026-11-01T12:45:00Z'))
      assert.match(display.membershipDate('2026-11-01'), /01.*Nov.*2026/)
    }
  } finally { if (previous === undefined) delete process.env.TZ; else process.env.TZ = previous }
})

test('My Access requests the IST month at the UTC/IST month boundary', async () => {
  const RealDate = globalThis.Date
  let path
  globalThis.__istRequest = async p => { path = p; return { days: [] } }
  try {
    globalThis.Date = class extends RealDate { constructor(...args) { super(...(args.length ? args : ['2026-10-31T18:30:00Z'])) } }
    await account.accessService.current()
    assert.equal(path, '/customer/access-calendar?year=2026&month=11')
  } finally { globalThis.Date = RealDate }
})

test('calendar export identifies Asia/Kolkata and booking UI never labels UTC', () => {
  const detail = readFileSync(new URL('../src/pages/booking/BookingDetailPage.tsx', import.meta.url), 'utf8')
  assert.match(detail, /DTSTART;TZID=Asia\/Kolkata:/)
  assert.match(detail, /TZOFFSETTO:\+0530/)
  for (const file of ['BookingPage', 'BookingAccess']) {
    assert.doesNotMatch(readFileSync(new URL(`../src/pages/booking/${file}.tsx`, import.meta.url), 'utf8'), /\bUTC\b/)
  }
})