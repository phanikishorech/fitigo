import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const source = readFileSync(new URL('../src/utils/booking.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { isFutureBookingStart, minimumBookingStart, gymStartOptions, oneHourVisitEnd } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
const now = Date.parse('2026-10-08T12:00:30+05:30')

test('past date, elapsed start, current minute and malformed inputs are not bookable', () => {
  for (const [date, time] of [['2026-10-07', '23:59'], ['2026-10-08', '11:00'], ['2026-10-08', '12:00'], ['2026-10-08', '12:00:30'], ['', ''], ['2026-10-08', '12:00+05:30']]) {
    assert.equal(isFutureBookingStart(date, time, now), false)
  }
})
test('future start and next UTC day are bookable', () => {
  assert.equal(isFutureBookingStart('2026-10-08', '12:01', now), true)
  assert.equal(isFutureBookingStart('2026-10-09', '00:00', Date.parse('2026-10-08T23:59:59+05:30')), true)
})
test('same input uses UTC independently of browser timezone', () => {
  const previous = process.env.TZ
  try {
    for (const zone of ['UTC', 'Asia/Kolkata', 'America/Los_Angeles']) {
      process.env.TZ = zone
      assert.equal(isFutureBookingStart('2026-10-08', '12:01', now), true)
      assert.equal(isFutureBookingStart('2026-10-08', '12:00', now), false)
    }
  } finally { if (previous === undefined) delete process.env.TZ; else process.env.TZ = previous }
})
test('time input minimum advances to next minute or opening time', () => {
  assert.equal(minimumBookingStart('2026-10-08', '06:00:00', now), '12:01')
  assert.equal(minimumBookingStart('2026-10-08', '14:00:00', now), '14:00')
  assert.equal(minimumBookingStart('2026-10-09', '06:00:00', now), '06:00')
})
test('booking form and checkout keep backend rejection visible', () => {
  const page = readFileSync(new URL('../src/pages/booking/BookingPage.tsx', import.meta.url), 'utf8')
  assert.match(page, /server_now/)
  assert.match(page, /disabled=\{!futureStart/)
  assert.match(page, /bookingNow\(Date.now\(\)\)/)
  const checkout = readFileSync(new URL('../src/pages/booking/CartPage.tsx', import.meta.url), 'utf8')
  assert.match(checkout, /catch \(error\) \{ setConfirm\(false\); throw error \}/)
})

test('quarter-hour choices exclude past times and preserve full one-hour duration', () => {
  assert.deepEqual(gymStartOptions('2026-10-08', '06:00:00', '14:00:00', now), ['12:15', '12:30', '12:45', '13:00'])
  assert.deepEqual(gymStartOptions('2026-10-09', '06:10:00', '07:45:00', now), ['06:15', '06:30', '06:45'])
  assert.deepEqual(gymStartOptions('2026-10-08', '06:00', '14:00', now), ['12:15', '12:30', '12:45', '13:00'])
  assert.deepEqual(gymStartOptions('2026-10-07', '06:00', '23:00', now), [])
  assert.deepEqual(gymStartOptions('2026-10-09', null, '23:00', now), [])
})
test('automatic end is exactly an hour and never wraps to another date', () => {
  for (const minute of ['00', '15', '30', '45']) assert.equal(oneHourVisitEnd(`18:${minute}`), `19:${minute}`)
  for (const invalid of ['18:01', '18:15:01', '', '23:00', '24:00']) assert.equal(oneHourVisitEnd(invalid), '')
})
test('preferred gym start uses dropdowns with no editable end time', () => {
  const page = readFileSync(new URL('../src/pages/booking/BookingPage.tsx', import.meta.url), 'utf8')
  assert.match(page, /aria-label="Start hour \(IST\)"/)
  assert.match(page, /aria-label="Start minutes"/)
  assert.doesNotMatch(page, /type="time"|preferred_end_time:/)
  assert.match(page, /end time set automatically/)
})