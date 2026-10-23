export type DateRange = { date_from: string; date_to: string }
export type DatePreset = 'today' | 'yesterday' | 'week' | 'month' | 'last30' | 'custom'
export const datePresets: { value: DatePreset; label: string }[] = [
  { value: 'today', label: 'Today' }, { value: 'yesterday', label: 'Yesterday' },
  { value: 'week', label: 'This week' }, { value: 'month', label: 'This month' },
  { value: 'last30', label: 'Last 30 days' }, { value: 'custom', label: 'Custom' }
]
const dayMs = 86400000
function validDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value <= '0001-01-01' || value >= '9999-12-31') return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
}
export function rangeDays(range: DateRange) {
  return Math.round((Date.parse(`${range.date_to}T00:00:00Z`) - Date.parse(`${range.date_from}T00:00:00Z`)) / dayMs) + 1
}
export function rangeError(range: DateRange) {
  if (!validDate(range.date_from) || !validDate(range.date_to)) return 'Enter a valid start and end date.'
  if (range.date_from > range.date_to) return 'Start date must not be after end date.'
  if (rangeDays(range) > 366) return 'Select a date range of at most 366 days.'
  return ''
}
export function presetRange(preset: Exclude<DatePreset, 'custom'>, today: string): DateRange {
  const day = new Date(`${today}T00:00:00Z`)
  let offset = 0
  if (preset === 'yesterday') offset = 1
  if (preset === 'week') offset = (day.getUTCDay() + 6) % 7
  if (preset === 'month') offset = day.getUTCDate() - 1
  if (preset === 'last30') offset = 29
  const start = new Date(day.getTime() - offset * dayMs).toISOString().slice(0, 10)
  return { date_from: start, date_to: preset === 'yesterday' ? start : today }
}