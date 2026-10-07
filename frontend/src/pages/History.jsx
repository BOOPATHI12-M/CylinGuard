/**
 * The readings table.
 *
 * Filtering and pagination both happen in SQL. That is not an optimisation, it is
 * correctness: a "gas exceeded" filter applied to the 50 fetched rows would report
 * nothing wrong on a day whose only leak sits on page 4.
 *
 * There is no free-text search box. A reading is four numbers and a timestamp - there is
 * no text to search - so the filters are the date window, the device state and whether
 * the gas reading crossed its threshold. A search field that silently matched nothing
 * would be worse than its absence.
 */

import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Filter, RotateCcw, Table } from 'lucide-react'

import { EmptyState, ErrorState } from '../components/EmptyState'
import { TableSkeleton } from '../components/LoadingSkeleton'
import { StatusBadge } from '../components/StatusBadge'
import { useResource } from '../hooks/useResource'
import { monitoring } from '../services/api'

const PAGE_SIZES = [25, 50, 100]
const GAS_FILTERS = [
  { id: 'all', label: 'All readings', value: undefined },
  { id: 'exceeded', label: 'Gas over threshold', value: true },
  { id: 'safe', label: 'Gas below threshold', value: false },
]
const DEVICE_FILTERS = [
  { id: 'all', label: 'Any device state', value: undefined },
  { id: 'online', label: 'Online', value: 'ONLINE' },
  { id: 'offline', label: 'Offline', value: 'OFFLINE' },
]

export function History() {
  const { cylinderId } = useOutletContext()

  const [page, setPage] = useState(1)
  const [size, setSize] = useState(PAGE_SIZES[1])
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [gas, setGas] = useState(GAS_FILTERS[0])
  const [device, setDevice] = useState(DEVICE_FILTERS[0])

  // Any filter change invalidates the page number: staying on page 7 of a result set
  // that now has two pages shows an empty table and looks like a bug.
  useEffect(() => {
    setPage(1)
  }, [since, until, gas.id, device.id, size, cylinderId])

  const resource = useResource(
    () =>
      monitoring.history(cylinderId, {
        page,
        size,
        since: since || undefined,
        until: until || undefined,
        gasExceeded: gas.value,
        deviceStatus: device.value,
      }),
    [cylinderId, page, size, since, until, gas.id, device.id],
    { enabled: Boolean(cylinderId) },
  )

  const filtersActive = Boolean(since || until || gas.value !== undefined || device.value)

  const reset = () => {
    setSince('')
    setUntil('')
    setGas(GAS_FILTERS[0])
    setDevice(DEVICE_FILTERS[0])
  }

  return (
    <div className="space-y-4">
      <section aria-labelledby="filters-heading" className="glass p-4">
        <div className="flex items-center gap-2">
          <Filter aria-hidden="true" className="h-4 w-4 text-ink-faint" />
          <h2 id="filters-heading" className="text-sm font-semibold text-ink">
            Filters
          </h2>
          {filtersActive ? (
            <button type="button" onClick={reset} className="btn-ghost ml-auto text-xs">
              <RotateCcw aria-hidden="true" className="h-3.5 w-3.5" />
              Clear
            </button>
          ) : null}
        </div>

        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label htmlFor="since" className="label">From</label>
            <input
              id="since"
              type="datetime-local"
              value={since}
              onChange={(event) => setSince(event.target.value)}
              className="field"
            />
          </div>
          <div>
            <label htmlFor="until" className="label">To</label>
            <input
              id="until"
              type="datetime-local"
              value={until}
              onChange={(event) => setUntil(event.target.value)}
              className="field"
            />
          </div>
          <div>
            <label htmlFor="gas-filter" className="label">Gas</label>
            <select
              id="gas-filter"
              value={gas.id}
              onChange={(event) => setGas(GAS_FILTERS.find((f) => f.id === event.target.value))}
              className="field"
            >
              {GAS_FILTERS.map((filter) => (
                <option key={filter.id} value={filter.id}>{filter.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="device-filter" className="label">Device</label>
            <select
              id="device-filter"
              value={device.id}
              onChange={(event) =>
                setDevice(DEVICE_FILTERS.find((f) => f.id === event.target.value))
              }
              className="field"
            >
              {DEVICE_FILTERS.map((filter) => (
                <option key={filter.id} value={filter.id}>{filter.label}</option>
              ))}
            </select>
          </div>
        </div>

        <p className="mt-3 text-[11px] leading-relaxed text-ink-faint">
          Filters are applied by the database across the whole history, not just the rows on
          this page. The gas filter compares against the threshold currently configured.
        </p>
      </section>

      {resource.loading && !resource.data ? (
        <TableSkeleton rows={8} columns={6} />
      ) : resource.error ? (
        <ErrorState
          title="History unavailable"
          description={resource.error.message}
          onRetry={resource.reload}
        />
      ) : resource.data.total === 0 ? (
        <EmptyState
          icon={Table}
          title={filtersActive ? 'No readings match these filters' : 'No readings recorded'}
          description={
            filtersActive
              ? 'Try widening the date range or clearing a filter.'
              : 'Connect the device, or turn on demo mode to generate a history.'
          }
        />
      ) : (
        <>
          <section aria-labelledby="readings-heading" className="glass overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hairline px-5 py-3">
              <h2 id="readings-heading" className="text-sm font-semibold text-ink">
                Readings
              </h2>
              <p className="tabular text-xs text-ink-muted" aria-live="polite">
                {resource.data.total.toLocaleString()} rows · page {resource.data.page} of{' '}
                {resource.data.pages}
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[46rem] text-sm">
                <caption className="sr-only">
                  Sensor readings, newest first. Columns: time, total weight, LPG remaining,
                  percentage, gas reading and device state.
                </caption>
                <thead>
                  <tr className="border-b border-hairline text-left text-[11px] uppercase tracking-wider text-ink-muted">
                    <th scope="col" className="px-5 py-2.5 font-medium">Time</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">Total weight</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">LPG left</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">Level</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">Gas</th>
                    <th scope="col" className="px-5 py-2.5 font-medium">Device</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline/60">
                  {resource.data.items.map((row) => (
                    <tr key={row.id}>
                      <td className="tabular whitespace-nowrap px-5 py-2.5 text-ink-muted">
                        {new Date(row.timestamp).toLocaleString()}
                      </td>
                      <td className="tabular whitespace-nowrap px-3 py-2.5 text-ink">
                        {row.total_weight_kg} kg
                      </td>
                      <td className="tabular whitespace-nowrap px-3 py-2.5 text-ink">
                        {row.remaining_kg} kg
                      </td>
                      <td className="tabular whitespace-nowrap px-3 py-2.5 text-ink-muted">
                        {row.percentage}%
                      </td>
                      <td className="tabular whitespace-nowrap px-3 py-2.5">
                        <span className="text-ink">{row.gas_sensor_value}</span>{' '}
                        {row.gas_status !== 'SAFE' ? (
                          <StatusBadge state={row.gas_status} size="sm" className="ml-1" />
                        ) : null}
                      </td>
                      <td className="whitespace-nowrap px-5 py-2.5">
                        <div className="flex items-center gap-1.5">
                          <StatusBadge state={row.device_status} size="sm" />
                          {row.is_simulated ? (
                            <span className="text-[10px] uppercase text-demo" title="Generated by the simulator">
                              sim
                            </span>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <nav
            aria-label="History pages"
            className="flex flex-wrap items-center justify-between gap-3"
          >
            <div className="flex items-center gap-2">
              <label htmlFor="page-size" className="text-xs text-ink-muted">
                Rows per page
              </label>
              <select
                id="page-size"
                value={size}
                onChange={(event) => setSize(Number(event.target.value))}
                className="rounded-xl2 border border-hairline bg-surface-raised/60 px-2.5 py-1.5 text-xs text-ink"
              >
                {PAGE_SIZES.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                disabled={resource.data.page <= 1}
                className="btn-ghost text-xs"
              >
                <ChevronLeft aria-hidden="true" className="h-4 w-4" />
                Previous
              </button>
              <button
                type="button"
                onClick={() => setPage((current) => current + 1)}
                disabled={resource.data.page >= resource.data.pages}
                className="btn-ghost text-xs"
              >
                Next
                <ChevronRight aria-hidden="true" className="h-4 w-4" />
              </button>
            </div>
          </nav>
        </>
      )}
    </div>
  )
}
