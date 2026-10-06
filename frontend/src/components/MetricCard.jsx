/**
 * One number, its unit, and what it means.
 *
 * `value` is always passed in from an API response. There is no default value and no
 * placeholder figure, so a card cannot accidentally ship a hardcoded number: with
 * nothing to show it renders an em dash.
 */

import { StatusBadge } from './StatusBadge'

export function MetricCard({
  label,
  value,
  unit,
  hint,
  state,
  icon: Icon,
  tone = 'default',
  className = '',
}) {
  const accent =
    tone === 'danger'
      ? 'shadow-glow-danger'
      : tone === 'accent'
        ? 'shadow-glow-accent'
        : ''

  const missing = value === null || value === undefined || value === ''

  return (
    <div className={`glass p-4 sm:p-5 ${accent} ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">{label}</p>
        {Icon ? <Icon aria-hidden="true" className="h-4 w-4 shrink-0 text-ink-faint" /> : null}
      </div>

      <p className="mt-2 flex items-baseline gap-1.5">
        <span className="tabular text-2xl font-semibold text-ink sm:text-3xl">
          {missing ? '—' : value}
        </span>
        {unit && !missing ? (
          <span className="text-sm font-medium text-ink-muted">{unit}</span>
        ) : null}
      </p>

      {state ? <StatusBadge state={state} size="sm" className="mt-3" /> : null}
      {hint ? <p className="mt-2 text-xs leading-relaxed text-ink-faint">{hint}</p> : null}
    </div>
  )
}
