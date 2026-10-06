/**
 * A state, rendered as icon + word + colour.
 *
 * This component is how spec §59 is enforced rather than remembered: there is no prop
 * that produces a bare coloured dot. A green dot always carries the word SAFE, so the
 * state survives colour-blindness, phone glare and a washed-out projector at a demo.
 *
 * The words come from the backend (`lpg.status`, `gas.status`, `anomaly_state`,
 * `device.status`), so the UI never invents a state the API did not report. An unknown
 * value is shown verbatim in a neutral tone instead of being swallowed - a state we
 * forgot to style should be visible, not invisible.
 */

import {
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  Flame,
  Siren,
  TrendingUp,
  WifiOff,
} from 'lucide-react'

const TONES = {
  safe: 'bg-safe-soft text-safe border-safe/30',
  warn: 'bg-warn-soft text-warn border-warn/30',
  danger: 'bg-danger-soft text-danger border-danger/30',
  neutral: 'bg-surface-overlay/70 text-ink-muted border-hairline',
  demo: 'bg-demo-soft text-demo border-demo/30',
}

/** state word -> { tone, icon, label }. Labels are the words a user should read. */
const STATES = {
  NORMAL: { tone: 'safe', icon: CheckCircle2, label: 'NORMAL' },
  SAFE: { tone: 'safe', icon: CheckCircle2, label: 'SAFE' },
  ONLINE: { tone: 'safe', icon: CheckCircle2, label: 'ONLINE' },

  LOW: { tone: 'warn', icon: AlertTriangle, label: 'LOW' },
  UNUSUAL_CONSUMPTION: { tone: 'warn', icon: TrendingUp, label: 'UNUSUAL USE' },
  WARNING: { tone: 'warn', icon: AlertTriangle, label: 'WARNING' },

  CRITICAL: { tone: 'danger', icon: Siren, label: 'CRITICAL' },
  // "POSSIBLE" is kept in the words: the MQ-6 is a prototype detector, and the UI must
  // not upgrade a suspicion into a statement of fact.
  POSSIBLE_LEAK: { tone: 'danger', icon: Flame, label: 'POSSIBLE LEAK' },
  CRITICAL_LEAK: { tone: 'danger', icon: Siren, label: 'CRITICAL LEAK' },
  GAS_THRESHOLD_EXCEEDED: { tone: 'danger', icon: Flame, label: 'GAS DETECTED' },

  OFFLINE: { tone: 'neutral', icon: WifiOff, label: 'OFFLINE' },
  INFO: { tone: 'neutral', icon: CheckCircle2, label: 'INFO' },
}

export function StatusBadge({ state, size = 'md', className = '', title }) {
  const known = STATES[state]
  const tone = known?.tone ?? 'neutral'
  const Icon = known?.icon ?? CircleHelp
  // Underscores would otherwise read as code rather than language.
  const label = known?.label ?? String(state ?? 'UNKNOWN').replace(/_/g, ' ')

  const sizing =
    size === 'sm'
      ? 'px-2 py-0.5 text-[11px] gap-1'
      : size === 'lg'
        ? 'px-3.5 py-2 text-sm gap-2'
        : 'px-2.5 py-1 text-xs gap-1.5'

  return (
    <span
      className={`inline-flex items-center rounded-full border font-semibold uppercase tracking-wide ${TONES[tone]} ${sizing} ${className}`}
      title={title}
    >
      {/* aria-hidden: the word beside it is already the accessible name, so a screen
          reader should not announce the icon twice. */}
      <Icon aria-hidden="true" className={size === 'lg' ? 'h-4 w-4' : 'h-3.5 w-3.5'} />
      {label}
    </span>
  )
}

/** The amber badge shown whenever a reading came from the simulator. */
export function DemoBadge({ className = '' }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border border-demo/30 bg-demo-soft px-2.5 py-1 text-xs font-semibold uppercase tracking-wide text-demo ${className}`}
      title="Readings are generated, not measured by hardware"
    >
      <span aria-hidden="true">🟡</span> DEMO MODE
    </span>
  )
}

/** Shown on a prediction that came from arithmetic rather than a trained model. */
export function EstimateBadge({ isEstimate, className = '' }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${
        isEstimate ? 'border-hairline bg-surface-overlay/70 text-ink-muted' : TONES.safe
      } ${className}`}
      title={
        isEstimate
          ? 'Arithmetic estimate: remaining gas divided by the average daily use'
          : 'Produced by the trained prediction model'
      }
    >
      {isEstimate ? 'ESTIMATE' : 'POWERED BY ML'}
    </span>
  )
}
