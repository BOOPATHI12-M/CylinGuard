/**
 * Loading placeholders.
 *
 * Shaped like the content they stand in for, so the layout does not jump when data
 * lands. `role="status"` with an accessible label means a screen reader hears "loading"
 * rather than silence; `aria-hidden` on the bars keeps it from reading out a list of
 * meaningless boxes.
 */

function Bar({ className = '' }) {
  return (
    <div
      aria-hidden="true"
      className={`relative overflow-hidden rounded-lg bg-surface-overlay/60 ${className}`}
    >
      {/* The shimmer is decoration; prefers-reduced-motion disables it globally. */}
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/5 to-transparent" />
    </div>
  )
}

export function LoadingSkeleton({ lines = 3, className = '', label = 'Loading' }) {
  return (
    <div className={`space-y-2.5 ${className}`} role="status" aria-label={label}>
      {Array.from({ length: lines }).map((_, index) => (
        <Bar key={index} className={`h-4 ${index === lines - 1 ? 'w-2/3' : 'w-full'}`} />
      ))}
      <span className="sr-only">{label}…</span>
    </div>
  )
}

export function CardSkeleton({ className = '' }) {
  return (
    <div className={`glass p-5 ${className}`} role="status" aria-label="Loading">
      <Bar className="h-3 w-24" />
      <Bar className="mt-3 h-8 w-32" />
      <Bar className="mt-3 h-3 w-40" />
      <span className="sr-only">Loading…</span>
    </div>
  )
}

export function TableSkeleton({ rows = 6, columns = 5 }) {
  return (
    <div className="glass overflow-hidden" role="status" aria-label="Loading table">
      <div className="border-b border-hairline p-3">
        <Bar className="h-3 w-32" />
      </div>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="grid gap-3 border-b border-hairline/60 p-3 last:border-0"
             style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
          {Array.from({ length: columns }).map((_, cellIndex) => (
            <Bar key={cellIndex} className="h-3.5" />
          ))}
        </div>
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  )
}
