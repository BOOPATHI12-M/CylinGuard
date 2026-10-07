/**
 * Consumption over time.
 *
 * The weekly series is grouped in the browser from the daily rows the API returns, not
 * fetched separately. That is honest - it is an aggregate of data already on screen -
 * and it avoids a second endpoint whose only job is to add seven numbers together.
 */

import { useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { Activity, CalendarDays, Gauge, TrendingUp } from 'lucide-react'

import { ConsumptionChart } from '../charts/ConsumptionChart'
import { DateRangeSelector, RANGES } from '../components/DateRangeSelector'
import { EmptyState, ErrorState } from '../components/EmptyState'
import { CardSkeleton, LoadingSkeleton } from '../components/LoadingSkeleton'
import { MetricCard } from '../components/MetricCard'
import { useResource } from '../hooks/useResource'
import { monitoring } from '../services/api'

/** Monday-anchored ISO week key, so a week does not shift with the locale. */
function weekKey(dateString) {
  const date = new Date(dateString)
  const day = (date.getDay() + 6) % 7
  const monday = new Date(date)
  monday.setDate(date.getDate() - day)
  return monday.toISOString().slice(0, 10)
}

export function Consumption() {
  const { cylinderId } = useOutletContext()
  const [range, setRange] = useState(RANGES[1]) // 30D

  const resource = useResource(
    () => monitoring.consumption(cylinderId, range.days),
    [cylinderId, range.days],
    { enabled: Boolean(cylinderId) },
  )

  const weekly = useMemo(() => {
    const daily = resource.data?.daily ?? []
    const buckets = new Map()
    for (const row of daily) {
      const key = weekKey(row.record_date)
      const bucket = buckets.get(key) ?? { record_date: key, consumption_kg: 0, days: 0 }
      bucket.consumption_kg += Number(row.consumption_kg)
      bucket.days += 1
      buckets.set(key, bucket)
    }
    return [...buckets.values()]
      .sort((a, b) => a.record_date.localeCompare(b.record_date))
      .map((bucket) => ({
        record_date: bucket.record_date,
        consumption_kg: Number(bucket.consumption_kg.toFixed(3)),
        // The per-day average inside the week, so a partial week is not read as a
        // sudden drop in usage.
        daily_average_kg: Number((bucket.consumption_kg / bucket.days).toFixed(3)),
      }))
  }, [resource.data])

  if (resource.loading && !resource.data) {
    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
        <LoadingSkeleton lines={6} label="Loading consumption history" />
      </div>
    )
  }

  if (resource.error) {
    return (
      <ErrorState
        title="Consumption unavailable"
        description={resource.error.message}
        onRetry={resource.reload}
      />
    )
  }

  const { summary, daily } = resource.data

  return (
    <div className="space-y-5">
      <section aria-label="Consumption totals">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard label="Today" value={summary.today_kg} unit="kg" icon={Activity} />
          <MetricCard label="Last 7 days" value={summary.last_7_days_kg} unit="kg" icon={CalendarDays} />
          <MetricCard label="Last 30 days" value={summary.last_30_days_kg} unit="kg" icon={CalendarDays} />
          <MetricCard
            label="Daily average"
            value={summary.average_daily_kg}
            unit="kg"
            icon={Gauge}
            hint={`Over ${summary.days_of_history} days of history`}
          />
        </div>
      </section>

      <section aria-labelledby="daily-heading" className="glass p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="daily-heading" className="text-sm font-semibold text-ink">
            Daily consumption
          </h2>
          <DateRangeSelector value={range.id} onChange={setRange} />
        </div>

        <div className="mt-4">
          {daily.length ? (
            <ConsumptionChart daily={daily} />
          ) : (
            <EmptyState
              title="No daily records in this range"
              description="Consumption is derived once there are readings on at least two different days."
            />
          )}
        </div>
        <p className="mt-3 text-[11px] leading-relaxed text-ink-faint">
          Bars are gas used that day. The line is the running daily average the depletion
          estimate is based on.
        </p>
      </section>

      {weekly.length > 1 ? (
        <section aria-labelledby="weekly-heading" className="glass p-5">
          <div className="flex items-center gap-2">
            <TrendingUp aria-hidden="true" className="h-4 w-4 text-ink-faint" />
            <h2 id="weekly-heading" className="text-sm font-semibold text-ink">
              Weekly totals
            </h2>
          </div>
          <div className="mt-4">
            <ConsumptionChart daily={weekly} height={220} />
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-ink-faint">
            Grouped from the same daily records, by ISO week starting Monday. The first and
            last weeks in a range are usually partial.
          </p>
        </section>
      ) : null}
    </div>
  )
}
