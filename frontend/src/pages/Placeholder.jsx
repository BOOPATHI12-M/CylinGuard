/**
 * Stands in for the seven feature pages until phase 5 builds them.
 *
 * It is not empty on purpose: it echoes the live WebSocket frame, so the shell can be
 * verified end to end - token, socket, fan-out, rendering - before any page exists. The
 * numbers shown come from the frame and nowhere else, which is also the rule the real
 * pages will follow.
 */

import { Construction } from 'lucide-react'
import { useOutletContext } from 'react-router-dom'

import { EmptyState } from '../components/EmptyState'
import { MetricCard } from '../components/MetricCard'
import { DeviceStatus } from '../components/DeviceStatus'
import { EstimateBadge, StatusBadge } from '../components/StatusBadge'

export function Placeholder({ title, note }) {
  const { frame, socketStatus } = useOutletContext()

  return (
    <div className="space-y-5">
      <EmptyState
        icon={Construction}
        title={`${title} lands in phase 5`}
        description={note}
      />

      {frame ? (
        <section aria-labelledby="live-proof" className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="live-proof" className="text-sm font-semibold text-ink">
              Live data reaching the shell
            </h2>
            <StatusBadge state={frame.lpg.status} size="sm" />
            {frame.prediction ? (
              <EstimateBadge isEstimate={frame.prediction.is_estimate} />
            ) : null}
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="LPG remaining"
              value={frame.lpg.remaining_kg}
              unit="kg"
              hint={`${frame.lpg.percentage}% of capacity`}
            />
            <MetricCard
              label="Gas sensor"
              value={frame.gas.value}
              state={frame.gas.status}
              hint={`Threshold ${frame.gas.threshold}`}
              tone={frame.gas.exceeded ? 'danger' : 'default'}
            />
            <MetricCard
              label="Used today"
              value={frame.consumption.today_kg}
              unit="kg"
              hint={`${frame.consumption.average_daily_kg} kg/day average`}
            />
            <MetricCard
              label="Days remaining"
              value={frame.prediction?.remaining_days ?? null}
              unit="days"
              hint={
                frame.prediction
                  ? `${frame.prediction.method} · confidence ${frame.prediction.confidence}`
                  : 'No prediction computed yet'
              }
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <DeviceStatus device={frame.device} socketStatus={socketStatus} />
            <div className="glass p-4">
              <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">
                Frame generated at
              </p>
              <p className="tabular mt-1.5 font-mono text-sm text-ink">{frame.generated_at}</p>
              <p className="mt-2 text-[11px] leading-relaxed text-ink-faint">
                Every number on this page came from that frame or a REST response. None of them is
                written into the component.
              </p>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  )
}
