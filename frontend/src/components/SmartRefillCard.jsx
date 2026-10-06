/**
 * The refill recommendation.
 *
 * **The buttons record intent locally and nothing else.** Real LPG ordering and payment
 * are explicitly out of scope, so there is no supplier API behind this and the copy does
 * not imply one. A button labelled "Order refill" that silently did nothing would be a
 * worse outcome than no button, so it says "Mark refill as ordered" and the card then
 * shows what the user noted and when.
 *
 * The recommendation comes from the backend's own numbers - days remaining against the
 * user's `prediction_threshold` - rather than a figure invented here.
 */

import { useEffect, useState } from 'react'
import { CalendarClock, CheckCircle2, PackageCheck, Truck } from 'lucide-react'

const STORAGE_KEY = 'cylinguard.refillIntent'

function readIntent(cylinderId) {
  try {
    const all = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')
    return all[cylinderId] ?? null
  } catch {
    return null
  }
}

function writeIntent(cylinderId, value) {
  try {
    const all = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')
    if (value) all[cylinderId] = value
    else delete all[cylinderId]
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
  } catch {
    /* a note that cannot persist is still shown for this session */
  }
}

export function SmartRefillCard({ cylinderId, prediction, percentage, threshold, className = '' }) {
  const [intent, setIntent] = useState(null)

  useEffect(() => {
    setIntent(readIntent(cylinderId))
  }, [cylinderId])

  const days = prediction?.remaining_days ?? null
  const depletion = prediction?.predicted_depletion_date ?? null
  const dueSoon = days !== null && threshold !== undefined && days <= threshold

  const record = () => {
    const value = { at: new Date().toISOString() }
    writeIntent(cylinderId, value)
    setIntent(value)
  }

  const clear = () => {
    writeIntent(cylinderId, null)
    setIntent(null)
  }

  return (
    <section
      aria-labelledby="refill-heading"
      className={`glass p-5 ${dueSoon ? 'shadow-glow-accent' : ''} ${className}`}
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl2 border ${
            dueSoon ? 'border-accent/30 bg-accent-soft text-accent' : 'border-hairline text-ink-muted'
          }`}
        >
          <Truck className="h-4 w-4" />
        </span>

        <div className="min-w-0 flex-1">
          <h2 id="refill-heading" className="text-sm font-semibold text-ink">
            Smart refill
          </h2>

          {days === null ? (
            <p className="mt-1 text-sm text-ink-muted">
              Not enough history yet to recommend a refill date.
            </p>
          ) : dueSoon ? (
            <p className="tabular mt-1 text-sm text-ink">
              About <span className="font-semibold">{days}</span> days of gas left, at or below your{' '}
              {threshold}-day threshold. Worth arranging a refill now.
            </p>
          ) : (
            <p className="tabular mt-1 text-sm text-ink-muted">
              About <span className="font-semibold text-ink">{days}</span> days of gas left
              {percentage !== null && percentage !== undefined ? ` (${percentage}%)` : ''}. No refill
              needed yet.
            </p>
          )}

          {depletion ? (
            <p className="mt-2 flex items-center gap-1.5 text-xs text-ink-muted">
              <CalendarClock aria-hidden="true" className="h-3.5 w-3.5" />
              Estimated to run out on{' '}
              <span className="tabular font-medium text-ink">{depletion}</span>
            </p>
          ) : null}

          <div className="mt-4 flex flex-wrap items-center gap-2">
            {intent ? (
              <>
                <span className="inline-flex items-center gap-1.5 rounded-xl2 border border-safe/30 bg-safe-soft px-3 py-2 text-xs font-medium text-safe">
                  <CheckCircle2 aria-hidden="true" className="h-3.5 w-3.5" />
                  Noted {new Date(intent.at).toLocaleDateString()}
                </span>
                <button type="button" onClick={clear} className="btn-ghost text-xs">
                  Clear note
                </button>
              </>
            ) : (
              <button type="button" onClick={record} className="btn-primary text-xs">
                <PackageCheck aria-hidden="true" className="h-4 w-4" />
                Mark refill as ordered
              </button>
            )}
          </div>

          <p className="mt-3 text-[11px] leading-relaxed text-ink-faint">
            This is a note to yourself, kept in this browser. CylinGuard does not contact a supplier
            or place an order.
          </p>
        </div>
      </div>
    </section>
  )
}
