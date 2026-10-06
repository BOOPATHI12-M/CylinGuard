/**
 * The critical-state banner (spec §57).
 *
 * The most carefully worded component in the app. Three rules it must not break:
 *
 * 1. **It never claims a gas shutoff happened.** The relay field says what the backend
 *    *commanded*. The relay may be jammed, unwired, or the board unplugged. So the copy
 *    reads "shutoff relay commanded" and the word "commanded" is not decoration.
 * 2. **It never upgrades a suspicion to a fact.** POSSIBLE LEAK stays possible. The
 *    MQ-6 is a prototype detector, not a certified analyser, and the banner says so.
 * 3. **It tells the user what to do.** A red bar that only announces a state leaves
 *    someone standing in a room that may be filling with gas.
 *
 * The pulse is opacity-only and disabled under prefers-reduced-motion; the words and
 * the colour both remain, so nothing is carried by the animation alone.
 */

import { Flame, Siren, X } from 'lucide-react'

import { StatusBadge } from './StatusBadge'

const COPY = {
  POSSIBLE_LEAK: {
    icon: Flame,
    heading: 'Possible gas leak detected',
    body: 'The MQ-6 sensor is reading above its threshold. Ventilate the area, do not use switches or flames, and close the cylinder valve by hand.',
  },
  CRITICAL_LEAK: {
    icon: Siren,
    heading: 'Critical gas leak suspected',
    body: 'Gas is detected and consumption is abnormal. Leave the area, ventilate it, and close the cylinder valve by hand once it is safe to do so.',
  },
  GAS_THRESHOLD_EXCEEDED: {
    icon: Flame,
    heading: 'Gas detected above threshold',
    body: 'The MQ-6 sensor is reading above its configured threshold. Ventilate the area and check for a leak before resuming use.',
  },
  CRITICAL: {
    icon: Siren,
    heading: 'LPG critically low',
    body: 'The cylinder is close to empty. Arrange a refill now to avoid running out mid-use.',
  },
}

export function EmergencyBanner({ state, gasValue, gasThreshold, relayStatus, buzzerStatus, onDismiss }) {
  const copy = COPY[state]
  if (!copy) return null

  const Icon = copy.icon
  const isLeak = state === 'POSSIBLE_LEAK' || state === 'CRITICAL_LEAK' || state === 'GAS_THRESHOLD_EXCEEDED'

  return (
    <div
      // role=alert announces immediately and is the right level for this: it is the one
      // thing in the app that should interrupt whatever the user was reading.
      role="alert"
      aria-live="assertive"
      className="animate-fade-in-up rounded-xl2 border border-danger/50 bg-danger-soft shadow-glow-danger"
    >
      <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start">
        <Icon
          aria-hidden="true"
          className="h-6 w-6 shrink-0 animate-pulse-alarm text-danger motion-reduce:animate-none"
        />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold text-danger sm:text-base">{copy.heading}</h2>
            <StatusBadge state={state} size="sm" />
          </div>

          <p className="mt-1.5 text-sm leading-relaxed text-ink">{copy.body}</p>

          {isLeak && gasValue !== undefined ? (
            <p className="tabular mt-2 text-xs text-ink-muted">
              MQ-6 reading <span className="font-semibold text-ink">{gasValue}</span> against a
              threshold of <span className="font-semibold text-ink">{gasThreshold}</span>.
              {buzzerStatus ? <> Buzzer commanded <strong>{buzzerStatus}</strong>.</> : null}
              {relayStatus ? <> Shutoff relay commanded <strong>{relayStatus}</strong>.</> : null}
            </p>
          ) : null}

          {isLeak ? (
            <p className="mt-2 text-[11px] leading-relaxed text-ink-faint">
              The MQ-6 is a prototype detector, not a certified gas analyser. Relay and buzzer
              states shown are what the backend commanded — not a confirmed physical gas shutoff.
            </p>
          ) : null}
        </div>

        {onDismiss ? (
          <button
            type="button"
            onClick={onDismiss}
            className="self-start rounded p-1 text-ink-muted hover:text-ink"
            aria-label="Dismiss this warning"
          >
            <X aria-hidden="true" className="h-4 w-4" />
          </button>
        ) : null}
      </div>
    </div>
  )
}
