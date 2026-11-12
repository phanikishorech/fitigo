export function comparison(current: number, previous: number): string {
  if (!previous) return current ? 'No previous activity to compare' : 'No change from previous period'
  const delta = (current - previous) * 100 / previous
  return `${delta > 0 ? '+' : ''}${delta.toFixed(1)}% vs previous period`
}

// Excel/Sheets formula injection protection, including leading whitespace.
export function csvCell(value: unknown): string {
  let text = value == null ? '' : String(value)
  if (/^[\s]*[=+\-@]/.test(text) || /^[\t\r\n]/.test(text)) text = `'${text}`
  return `"${text.replaceAll('"', '""')}"`
}
export function analyticsCsv(headers: string[], rows: unknown[][]): string {
  return '\uFEFF' + [headers, ...rows].map(row => row.map(csvCell).join(',')).join('\r\n')
}