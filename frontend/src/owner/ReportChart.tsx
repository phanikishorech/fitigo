import { useId, useState } from 'react'
import { dateLabel, money } from '../services/client'
import type { SeriesPoint } from './analyticsService'
import { EmptyState } from './UI'

export default function ReportChart({ points, metric, title }: { points: SeriesPoint[]; metric: 'visits' | 'revenue'; title: string }) {
  const id = useId()
  const [active, setActive] = useState<number | null>(null)
  const values = points.map(point => Number(point[metric]))
  const maximum = Math.max(1, ...values)
  const ticks = metric === 'visits' ? [...new Set([0, Math.ceil(maximum / 2), maximum])] : [0, maximum / 2, maximum]
  const format = (value: number) => metric === 'revenue' ? money(value) : value.toLocaleString('en-IN')
  if (!values.some(value => value > 0)) return <EmptyState title={`No ${metric === 'visits' ? 'completed visits' : 'recognized revenue'} in this period`} description="Try another reporting period or gym. No estimated values are shown." />
  const x = (index: number) => 75 + (points.length === 1 ? 310 : index * 620 / (points.length - 1))
  const y = (value: number) => 200 - value / maximum * 160
  const chosen = active === null ? null : points[active]
  return <div className="ow-chart">
    <svg viewBox="0 0 760 245" role="img" aria-labelledby={id}>
      <title id={id}>{title}. Exact values are available by focusing a point or opening the data table.</title>
      {ticks.map(value => <g key={value}><line x1="75" x2="695" y1={y(value)} y2={y(value)} className="ow-chart-grid" /><text x="68" y={y(value) + 4} textAnchor="end">{metric === 'visits' ? value : new Intl.NumberFormat('en-IN', { notation: 'compact' }).format(value)}</text></g>)}
      <polyline points={values.map((value, index) => `${x(index)},${y(value)}`).join(' ')} fill="none" className="ow-chart-line" />
      {points.map((point, index) => <g key={point.date}>
        <circle cx={x(index)} cy={y(values[index])} r="4" className="ow-chart-dot" />
        <circle cx={x(index)} cy={y(values[index])} r="11" fill="transparent" tabIndex={0} role="button" aria-label={`${dateLabel(point.date)}${point.date !== point.date_to ? ` to ${dateLabel(point.date_to)}` : ''}: ${format(values[index])}`} onFocus={() => setActive(index)} onMouseEnter={() => setActive(index)} onClick={() => setActive(index)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') setActive(index) }}><title>{dateLabel(point.date)}: {format(values[index])}</title></circle>
        {(index === 0 || index === points.length - 1 || index % Math.max(1, Math.ceil(points.length / 4)) === 0) && <text x={x(index)} y="230" textAnchor="middle">{dateLabel(point.date).replace(/,?\s\d{4}$/, '')}</text>}
      </g>)}
    </svg>
    <p className="ow-chart-tooltip" role="status">{chosen ? `${dateLabel(chosen.date)}${chosen.date !== chosen.date_to ? ` – ${dateLabel(chosen.date_to)}` : ''}: ${format(Number(chosen[metric]))}` : 'Tap, hover or focus a point for its exact value.'}</p>
    <details><summary>View chart data</summary><div className="ow-report-table" tabIndex={0}><table className="ow-table"><thead><tr><th>Period (IST)</th><th>{metric === 'visits' ? 'Completed visits' : 'Revenue (INR)'}</th></tr></thead><tbody>{points.map(point => <tr key={point.date}><td>{dateLabel(point.date)}{point.date !== point.date_to && ` – ${dateLabel(point.date_to)}`}</td><td>{format(Number(point[metric]))}</td></tr>)}</tbody></table></div></details>
  </div>
}