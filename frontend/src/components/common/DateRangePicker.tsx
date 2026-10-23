import { useId, useState } from 'react'
import { dateLabel, localDate } from '../../services/client'
import { datePresets, presetRange, rangeError, type DatePreset, type DateRange } from '../../utils/dateRange'
import { Button } from './UI'
import './dateRange.css'

export function dateRangeLabel(range: DateRange) {
  return `${dateLabel(range.date_from)}${range.date_from === range.date_to ? '' : ` – ${dateLabel(range.date_to)}`} · IST`
}

export default function DateRangePicker({ value, onChange }: { value: DateRange; onChange: (range: DateRange) => void }) {
  const [preset, setPreset] = useState<DatePreset>('today')
  const [draft, setDraft] = useState(value)
  const id = useId()
  const error = rangeError(draft)
  return <section className="fg-date-range" aria-label="Dashboard date range">
    <div className="fg-date-presets" role="group" aria-label="Date range presets">{datePresets.map(option => <button
      key={option.value} type="button" aria-pressed={preset === option.value}
      onClick={() => {
        setPreset(option.value)
        if (option.value === 'custom') setDraft(value)
        else { const next = presetRange(option.value, localDate()); setDraft(next); onChange(next) }
      }}>{option.label}</button>)}</div>
    {preset === 'custom' && <form className="fg-date-custom" onSubmit={event => { event.preventDefault(); if (!error) onChange(draft) }}>
      <label>Start date<input type="date" aria-label="Start date" required value={draft.date_from} aria-describedby={error ? id : undefined}
        onChange={event => setDraft({ ...draft, date_from: event.target.value })} /></label>
      <label>End date<input type="date" aria-label="End date" required value={draft.date_to} aria-describedby={error ? id : undefined}
        onChange={event => setDraft({ ...draft, date_to: event.target.value })} /></label>
      <Button type="submit" disabled={!!error}>Apply range</Button>
      {error && <p id={id} className="fg-date-error" role="alert">{error}</p>}
    </form>}
    <p className="fg-date-description" aria-live="polite">Showing {dateRangeLabel(value)}. Week starts Monday. Custom ranges: up to 366 days.</p>
  </section>
}