/**
 * The cylinder picker in the header.
 *
 * Renders as plain text when the account owns a single cylinder, which is the common
 * case: a dropdown with one option is noise, and it invites a user to look for choices
 * that are not there.
 */

import { ChevronDown } from 'lucide-react'

import { useCylinders } from '../context/CylinderContext'

export function CylinderSelector({ className = '' }) {
  const { cylinders, activeId, select } = useCylinders()

  if (cylinders.length === 0) return null

  if (cylinders.length === 1) {
    const only = cylinders[0]
    return (
      <p className={`truncate font-mono text-xs text-ink-muted ${className}`} title={only.cylinder_code}>
        {only.cylinder_code}
      </p>
    )
  }

  return (
    <div className={`relative ${className}`}>
      <label htmlFor="cylinder-select" className="sr-only">
        Select cylinder
      </label>
      <select
        id="cylinder-select"
        value={activeId ?? ''}
        onChange={(event) => select(Number(event.target.value))}
        className="appearance-none rounded-xl2 border border-hairline bg-surface-raised/60 py-1.5 pl-3 pr-8 font-mono text-xs text-ink"
      >
        {cylinders.map((row) => (
          <option key={row.id} value={row.id}>
            {row.cylinder_code}
            {/* The level is in the label so the choice can be made without opening
                each cylinder in turn. */}
            {row.has_readings ? ` — ${row.percentage}%` : ' — no data'}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint"
      />
    </div>
  )
}
