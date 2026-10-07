/**
 * The safety page.
 *
 * Every claim on this page is scoped to what is actually known:
 *
 * * the gas value is a raw MQ-6 ADC reading, labelled as such, not a concentration;
 * * buzzer and relay are what the backend *commanded*, and the column header says so;
 * * the sensor is named a prototype detector wherever a reader might assume otherwise.
 *
 * The live frame takes precedence over the fetched payload, so a leak appears here
 * without a refresh, exactly as on the dashboard.
 */

import { useOutletContext } from 'react-router-dom'
import { Bell, Flame, Power, ShieldCheck } from 'lucide-react'

import { EmergencyBanner } from '../components/EmergencyBanner'
import { EmptyState, ErrorState } from '../components/EmptyState'
import { CardSkeleton, TableSkeleton } from '../components/LoadingSkeleton'
import { MetricCard } from '../components/MetricCard'
import { StatusBadge } from '../components/StatusBadge'
import { useResource } from '../hooks/useResource'
import { monitoring } from '../services/api'

export function Safety() {
  const { cylinderId, frame } = useOutletContext()

  const resource = useResource(
    () => monitoring.safety(cylinderId, 50),
    [cylinderId],
    { enabled: Boolean(cylinderId) },
  )

  if (resource.loading && !resource.data) {
    return (
      <div className="space-y-4">
        <CardSkeleton />
        <TableSkeleton rows={5} columns={5} />
      </div>
    )
  }

  if (!resource.data) {
    if (resource.error?.status === 409) {
      return (
        <EmptyState
          icon={ShieldCheck}
          title="No readings yet"
          description="Safety state is derived from sensor readings. Connect the device, or turn on demo mode."
        />
      )
    }
    return (
      <ErrorState
        title="Safety state unavailable"
        description={resource.error?.message ?? 'Could not load the safety state.'}
        onRetry={resource.reload}
      />
    )
  }

  // The frame is fresher for the live values; the events list only changes on a
  // transition, so the fetched copy is fine for it.
  const gas = frame?.gas ?? resource.data.gas
  const buzzer = frame?.buzzer_status ?? resource.data.buzzer_status
  const relay = frame?.relay_status ?? resource.data.relay_status
  const events = resource.data.events

  const headroom = gas.threshold - gas.value

  return (
    <div className="space-y-5">
      {gas.exceeded ? (
        <EmergencyBanner
          state={gas.status}
          gasValue={gas.value}
          gasThreshold={gas.threshold}
          buzzerStatus={buzzer}
          relayStatus={relay}
        />
      ) : null}

      <section
        aria-labelledby="state-heading"
        className={`glass p-6 ${gas.exceeded ? 'shadow-glow-danger' : ''}`}
      >
        <div className="flex flex-col items-center gap-4 text-center sm:flex-row sm:text-left">
          <span
            aria-hidden="true"
            className={`grid h-16 w-16 shrink-0 place-items-center rounded-full border-2 ${
              gas.exceeded
                ? 'animate-pulse-alarm border-danger/50 bg-danger-soft text-danger motion-reduce:animate-none'
                : 'border-safe/40 bg-safe-soft text-safe'
            }`}
          >
            {gas.exceeded ? <Flame className="h-7 w-7" /> : <ShieldCheck className="h-7 w-7" />}
          </span>

          <div className="min-w-0 flex-1">
            <h2 id="state-heading" className="text-xs font-medium uppercase tracking-wider text-ink-muted">
              Current state
            </h2>
            <div className="mt-1.5 flex justify-center sm:justify-start">
              <StatusBadge state={gas.status} size="lg" />
            </div>
            <p className="tabular mt-2 text-sm text-ink-muted">
              {gas.exceeded ? (
                <>
                  MQ-6 at <span className="font-semibold text-ink">{gas.value}</span>, over the{' '}
                  {gas.threshold} threshold.
                </>
              ) : (
                <>
                  MQ-6 at <span className="font-semibold text-ink">{gas.value}</span> —{' '}
                  {headroom} below the {gas.threshold} threshold.
                </>
              )}
            </p>
          </div>
        </div>
      </section>

      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard
          label="Gas sensor (raw MQ-6)"
          value={gas.value}
          icon={Flame}
          state={gas.status}
          tone={gas.exceeded ? 'danger' : 'default'}
          hint={`Alarm threshold ${gas.threshold}`}
        />
        <MetricCard
          label="Buzzer (commanded)"
          value={buzzer}
          icon={Bell}
          hint="What the backend asked for, not a confirmed sound"
        />
        <MetricCard
          label="Shutoff relay (commanded)"
          value={relay}
          icon={Power}
          hint="Not a confirmed physical gas shutoff"
        />
      </div>

      <section aria-labelledby="events-heading" className="glass overflow-hidden">
        <div className="border-b border-hairline px-5 py-3">
          <h2 id="events-heading" className="text-sm font-semibold text-ink">
            Event history
          </h2>
          <p className="mt-0.5 text-[11px] text-ink-faint">
            One row per state change, not per reading — a sustained alarm is a single event.
          </p>
        </div>

        {events.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-ink-muted">
            No safety events recorded. Nothing has crossed the gas threshold.
          </div>
        ) : (
          // overflow-x on the wrapper, not the page: a wide table scrolls inside its own
          // card instead of forcing the whole layout sideways on a phone.
          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] text-sm">
              <caption className="sr-only">
                Safety events, newest first, with the gas reading and commanded actuator state
              </caption>
              <thead>
                <tr className="border-b border-hairline text-left text-[11px] uppercase tracking-wider text-ink-muted">
                  <th scope="col" className="px-5 py-2.5 font-medium">When</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">Event</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">Gas / threshold</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">Buzzer</th>
                  <th scope="col" className="px-5 py-2.5 font-medium">Relay</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline/60">
                {events.map((event) => (
                  <tr key={event.id}>
                    <td className="tabular whitespace-nowrap px-5 py-2.5 text-ink-muted">
                      {new Date(event.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusBadge
                        state={event.event_type === 'CLEARED' ? 'SAFE' : 'GAS_THRESHOLD_EXCEEDED'}
                        size="sm"
                      />
                    </td>
                    <td className="tabular whitespace-nowrap px-3 py-2.5 text-ink">
                      {event.gas_value} / {event.threshold}
                    </td>
                    <td className="px-3 py-2.5 text-ink-muted">{event.buzzer_status}</td>
                    <td className="px-5 py-2.5 text-ink-muted">{event.relay_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <p className="text-[11px] leading-relaxed text-ink-faint">
        The MQ-6 is a prototype detector, not a certified gas analyser, and the values above are
        raw ADC readings rather than a measured concentration. Buzzer and relay columns record what
        the backend commanded — a relay may be jammed, unwired or unpowered, so none of this
        confirms that gas stopped flowing. Treat an alarm as a reason to ventilate and check by
        hand, never as a completed safety action.
      </p>
    </div>
  )
}
