/**
 * The 7D / 30D / 3M range tabs.
 *
 * Built as a real radiogroup rather than styled buttons, so arrow keys move between
 * options the way a keyboard user expects and the selected option is announced. Only
 * the active tab is in the tab order (`tabIndex`), which is what makes a radiogroup one
 * stop rather than three.
 */

import { useRef } from 'react'

export const RANGES = [
  { id: '7d', label: '7D', days: 7, description: 'Last 7 days' },
  { id: '30d', label: '30D', days: 30, description: 'Last 30 days' },
  { id: '3m', label: '3M', days: 90, description: 'Last 3 months' },
]

export function DateRangeSelector({ value, onChange, ranges = RANGES, className = '' }) {
  const containerRef = useRef(null)

  const handleKeyDown = (event) => {
    const keys = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }
    const step = keys[event.key]
    if (!step) return

    event.preventDefault()
    const index = ranges.findIndex((range) => range.id === value)
    const next = ranges[(index + step + ranges.length) % ranges.length]
    onChange(next)
    // Move focus with the selection, or the ring would be left on the old option.
    containerRef.current?.querySelector(`[data-range="${next.id}"]`)?.focus()
  }

  return (
    <div
      ref={containerRef}
      role="radiogroup"
      aria-label="Date range"
      onKeyDown={handleKeyDown}
      className={`inline-flex rounded-xl2 border border-hairline bg-surface-raised/60 p-0.5 ${className}`}
    >
      {ranges.map((range) => {
        const selected = range.id === value
        return (
          <button
            key={range.id}
            type="button"
            role="radio"
            data-range={range.id}
            aria-checked={selected}
            aria-label={range.description}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(range)}
            className={`rounded-[0.9rem] px-3 py-1.5 text-xs font-semibold transition-colors ${
              selected ? 'bg-accent text-base' : 'text-ink-muted hover:text-ink'
            }`}
          >
            {range.label}
          </button>
        )
      })}
    </div>
  )
}
