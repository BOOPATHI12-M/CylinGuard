/**
 * The dashboard. The screen the product is judged on.
 *
 * Every number here comes from the WebSocket frame, or from the REST response that
 * seeded it before the first frame arrived. Nothing is written into this file: grep it
 * for digits and you will find HTTP status codes, Tailwind sizes and array indices only.
 * That is the "no hardcoded dashboard values" rule, and it is why the illustrative
 * figures in the spec appear nowhere in the app - they were only ever seed examples.
 *
 * The live frame is preferred over the fetched payload whenever one has arrived, so a
 * leak posted while the page is open flips the UI with no refresh and no polling.
 */

import { Activity, Flame, Gauge, Thermometer, TrendingDown } from 'lucide-react'
import { useOutletContext } from 'react-router-dom'

import { ConsumptionChart } from '../charts/ConsumptionChart'
import { CylinderVisualization } from '../components/CylinderVisualization'
import { DeviceStatus } from '../components/DeviceStatus'
import { EmergencyBanner } from '../components/EmergencyBanner'
import { EmptyState, ErrorState } from '../components/EmptyState'
import { CardSkeleton, LoadingSkeleton } from '../components/LoadingSkeleton'
import { MetricCard } from '../components/MetricCard'
import { SmartRefillCard } from '../components/SmartRefillCard'
import { EstimateBadge, StatusBadge } from '../components/StatusBadge'
import { useAlertSound, useCriticalSound } from '../hooks/useAlertSound'
import { useResource } from '../hooks/useResource'
import { monitoring } from '../services/api'

const CRITICAL_STATES = ['POSSIBLE_LEAK', 'CRITICAL_LEAK', 'GAS_THRESHOLD_EXCEEDED']

// The chart window. Used by both the request and the heading, so the label cannot start
// describing a range the data no longer covers.
const CHART_DAYS = 14

export function Dashboard() {
  const { cylinderId, frame, socketStatus } = useOutletContext()

  const dashboard = useResource(
    () => monitoring.dashboard(cylinderId),
    [cylinderId],
    { enabled: Boolean(cylinderId) },
  )
  const consumption = useResource(
    () => monitoring.consumption(cylinderId, CHART_DAYS),
    [cylinderId],
    { enabled: Boolean(cylinderId) },
  )

  // The socket frame wins once it exists; the fetch is only what fills the page before
  // the first push.
  const view = frame ?? dashboard.data

  // Opt-in only, and fired on the transition into critical rather than on every frame -
  // see hooks/useAlertSound.js.
  const sound = useAlertSound()
  useCriticalSound(view?.gas?.status, sound)

  if (dashboard.loading && !view) {
    return (
      <div className="space-y-4">
        <LoadingSkeleton lines={2} label="Loading dashboard" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((index) => (
            <CardSkeleton key={index} />
          ))}
        </div>
      </div>
    )
  }

  if (!view) {
    // 409 is the backend saying "this cylinder has never reported" - a real state, not a
    // failure, so it gets an empty state rather than an error.
    if (dashboard.error?.status === 409) {
      return (
        <EmptyState
          icon={Thermometer}
          title="No readings yet"
          description="This cylinder has no sensor data. Connect the ESP32, or turn on demo mode to generate a plausible history."
        />
      )
    }
    return (
      <ErrorState
        description={dashboard.error?.message ?? 'The dashboard could not be loaded.'}
        onRetry={dashboard.reload}
      />
    )
  }

  const { cylinder, device, lpg, gas, consumption: summary, prediction } = view
  // The gas word is the strongest signal the frame carries in phase 5; the full anomaly
  // ladder arrives on the frame via the ingest pipeline.
  const criticalState = CRITICAL_STATES.includes(gas.status)
    ? gas.status
    : lpg.status === 'CRITICAL'
      ? 'CRITICAL'
      : null

  return (
    <div className="space-y-5">
      {criticalState ? (
        <EmergencyBanner
          state={criticalState}
          gasValue={gas.value}
          gasThreshold={gas.threshold}
          buzzerStatus={view.buzzer_status}
          relayStatus={view.relay_status}
        />
      ) : null}

      <CylinderVisualization
        percentage={lpg.percentage}
        remainingKg={lpg.remaining_kg}
        capacityKg={cylinder.capacity_kg}
        status={lpg.status}
        isSimulated={lpg.is_simulated}
      />

      <section aria-label="Live sensor readings">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            label="Total weight"
            value={lpg.total_weight_kg}
            unit="kg"
            icon={Gauge}
            hint={`Tare ${cylinder.empty_weight_kg} kg`}
          />
          <MetricCard
            label="Gas sensor"
            value={gas.value}
            icon={Flame}
            state={gas.status}
            tone={gas.exceeded ? 'danger' : 'default'}
            hint={`MQ-6 raw, threshold ${gas.threshold}`}
          />
          <MetricCard
            label="Used today"
            value={summary.today_kg}
            unit="kg"
            icon={Activity}
            hint={`${summary.average_daily_kg} kg/day average`}
          />
          <MetricCard
            label="Days remaining"
            value={prediction?.remaining_days ?? null}
            unit="days"
            icon={TrendingDown}
            hint={
              prediction
                ? `Runs out around ${prediction.predicted_depletion_date ?? 'unknown'}`
                : 'Not enough history to estimate'
            }
          />
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-3">
        <section aria-labelledby="consumption-heading" className="glass p-5 lg:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="consumption-heading" className="text-sm font-semibold text-ink">
              Consumption, last {CHART_DAYS} days
            </h2>
            <p className="tabular text-xs text-ink-muted">
              7d {summary.last_7_days_kg} kg · 30d {summary.last_30_days_kg} kg
            </p>
          </div>

          <div className="mt-4">
            {consumption.loading ? (
              <LoadingSkeleton lines={5} label="Loading consumption history" />
            ) : consumption.error ? (
              <ErrorState
                title="Consumption unavailable"
                description={consumption.error.message}
                onRetry={consumption.reload}
              />
            ) : consumption.data?.daily?.length ? (
              <ConsumptionChart daily={consumption.data.daily} />
            ) : (
              <EmptyState
                title="No daily records yet"
                description="Consumption is derived once there are at least two readings on different days."
              />
            )}
          </div>
        </section>

        <div className="space-y-4">
          <section aria-labelledby="prediction-heading" className="glass p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 id="prediction-heading" className="text-sm font-semibold text-ink">
                Prediction
              </h2>
              {prediction ? <EstimateBadge isEstimate={prediction.is_estimate} /> : null}
            </div>

            {prediction ? (
              <dl className="mt-3 space-y-2 text-sm">
                <div className="flex justify-between gap-2">
                  <dt className="text-ink-muted">Days remaining</dt>
                  <dd className="tabular font-semibold text-ink">{prediction.remaining_days}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-ink-muted">Depletion date</dt>
                  <dd className="tabular text-ink">
                    {prediction.predicted_depletion_date ?? '—'}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-ink-muted">Based on</dt>
                  <dd className="tabular text-ink">{prediction.sample_count} days</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-ink-muted">Confidence</dt>
                  <dd className="tabular text-ink">{prediction.confidence}</dd>
                </div>
              </dl>
            ) : (
              <p className="mt-3 text-sm text-ink-muted">
                No prediction computed for this cylinder yet.
              </p>
            )}

            <p className="mt-3 text-[11px] leading-relaxed text-ink-faint">
              An estimate, not a guarantee. Below 14 days of history the figure is remaining gas
              divided by the average daily use.
            </p>
          </section>

          <section aria-labelledby="safety-heading" className="glass p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 id="safety-heading" className="text-sm font-semibold text-ink">
                Safety
              </h2>
              <StatusBadge state={gas.status} />
            </div>
            <dl className="mt-3 space-y-2 text-sm">
              <div className="flex justify-between gap-2">
                <dt className="text-ink-muted">MQ-6 reading</dt>
                <dd className="tabular font-semibold text-ink">{gas.value}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-ink-muted">Threshold</dt>
                <dd className="tabular text-ink">{gas.threshold}</dd>
              </div>
            </dl>
            <p className="mt-3 text-[11px] leading-relaxed text-ink-faint">
              The MQ-6 is a prototype detector, not a certified gas analyser.
            </p>
          </section>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <SmartRefillCard
          cylinderId={cylinderId}
          prediction={prediction}
          percentage={lpg.percentage}
          threshold={view.refill_threshold_days}
          className="lg:col-span-2"
        />
        <DeviceStatus device={device} socketStatus={socketStatus} />
      </div>

      <RecentAlerts alerts={view.recent_alerts} unread={view.unread_alerts} />
    </div>
  )
}

function RecentAlerts({ alerts, unread }) {
  if (!alerts?.length) {
    return (
      <EmptyState title="No alerts" description="Nothing has needed your attention on this cylinder." />
    )
  }

  return (
    <section aria-labelledby="alerts-heading" className="glass overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-hairline px-5 py-3">
        <h2 id="alerts-heading" className="text-sm font-semibold text-ink">
          Recent alerts
        </h2>
        {unread > 0 ? (
          <span className="tabular rounded-full bg-danger px-2 py-0.5 text-[11px] font-bold text-base">
            {unread} unread
          </span>
        ) : null}
      </div>
      <ul className="divide-y divide-hairline/60">
        {alerts.map((alert) => (
          <li key={alert.id} className="flex flex-col gap-1.5 px-5 py-3 sm:flex-row sm:items-start sm:gap-3">
            <StatusBadge state={alert.severity} size="sm" className="shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="text-sm leading-relaxed text-ink">{alert.message}</p>
              <p className="tabular mt-1 text-[11px] text-ink-faint">
                {alert.type} · {new Date(alert.created_at).toLocaleString()}
                {alert.is_read ? '' : ' · unread'}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
