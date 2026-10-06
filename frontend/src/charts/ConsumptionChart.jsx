/**
 * Daily consumption, as bars with the running average over them.
 *
 * Shared axis, tooltip and grid styling lives here so every chart in the app reads as
 * one system rather than three Recharts defaults.
 *
 * Two deliberate choices:
 *
 * * **A bar per day, not a smoothed line.** Consumption is a discrete daily total; a
 *   spline between days would imply values that were never measured.
 * * **The tooltip states the units.** "0.46" on its own is ambiguous between kg and a
 *   percentage, and the one thing a reader must not do with a safety product is guess.
 */

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const AXIS = {
  stroke: 'rgba(255,255,255,0.18)',
  tick: { fill: '#9BABC7', fontSize: 11 },
}

function shortDate(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="glass-raised px-3 py-2 text-xs">
      <p className="font-semibold text-ink">{shortDate(label)}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey} className="tabular mt-0.5 text-ink-muted">
          <span style={{ color: entry.color }}>■</span>{' '}
          {entry.dataKey === 'consumption_kg' ? 'Used' : 'Average'}:{' '}
          <span className="font-semibold text-ink">{entry.value}</span> kg
        </p>
      ))}
    </div>
  )
}

export function ConsumptionChart({ daily, height = 260 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={daily} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
        <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
        <XAxis
          dataKey="record_date"
          tickFormatter={shortDate}
          stroke={AXIS.stroke}
          tick={AXIS.tick}
          // Let Recharts drop labels rather than overlap them on a narrow phone.
          interval="preserveStartEnd"
          minTickGap={24}
        />
        <YAxis stroke={AXIS.stroke} tick={AXIS.tick} width={48} unit=" kg" />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
        <Bar dataKey="consumption_kg" fill="#38BDF8" radius={[4, 4, 0, 0]} maxBarSize={28} />
        <Line
          type="monotone"
          dataKey="daily_average_kg"
          stroke="#C4B5FD"
          strokeWidth={2}
          dot={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
