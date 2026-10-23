import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const source = readFileSync(new URL('../src/utils/dateRange.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { presetRange, rangeDays, rangeError, datePresets } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

test('all six requested range choices are available', () => {
  assert.deepEqual(datePresets.map(item => item.label), ['Today', 'Yesterday', 'This week', 'This month', 'Last 30 days', 'Custom'])
})
for (const [preset, today, start, end] of [
  ['today', '2026-10-19', '2026-10-19', '2026-10-19'],
  ['yesterday', '2026-01-01', '2025-12-31', '2025-12-31'],
  ['week', '2026-10-19', '2026-10-19', '2026-10-19'],
  ['week', '2026-10-25', '2026-10-19', '2026-10-25'],
  ['week', '2026-01-01', '2025-12-29', '2026-01-01'],
  ['month', '2026-10-19', '2026-10-01', '2026-10-19'],
  ['last30', '2026-10-19', '2026-09-20', '2026-10-19'],
  ['last30', '2024-03-01', '2024-02-01', '2024-03-01'],
]) test(`${preset} at ${today} is inclusive and calendar-correct`, () => {
  assert.deepEqual(presetRange(preset, today), { date_from: start, date_to: end })
})
test('range validation rejects incomplete, impossible, reversed and oversized ranges', () => {
  for (const [start, end] of [['', '2026-10-19'], ['2026-02-30', '2026-03-01'], ['2026-10-20', '2026-10-19'], ['2025-01-01', '2026-01-02'], ['0000-01-01', '0000-01-02'], ['9999-12-31', '9999-12-31']]) {
    assert.ok(rangeError({ date_from: start, date_to: end }), `${start} ${end}`)
  }
  assert.equal(rangeError({ date_from: '2024-01-01', date_to: '2024-12-31' }), '')
  assert.equal(rangeDays({ date_from: '2024-01-01', date_to: '2024-12-31' }), 366)
  assert.equal(rangeDays(presetRange('last30', '2026-10-19')), 30)
})
test('preset calculations do not depend on browser timezone', () => {
  const old = process.env.TZ
  try {
    for (const zone of ['UTC', 'America/Los_Angeles', 'Asia/Kolkata', 'Pacific/Auckland']) {
      process.env.TZ = zone
      assert.deepEqual(presetRange('week', '2026-03-08'), { date_from: '2026-03-02', date_to: '2026-03-08' })
    }
  } finally { if (old === undefined) delete process.env.TZ; else process.env.TZ = old }
})