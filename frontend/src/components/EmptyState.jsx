/**
 * Nothing to show, and why.
 *
 * Deliberately distinct from an error. "No readings yet" is a real state of the
 * product - a device that has not reported - and conflating it with a failure would
 * send a user hunting for a bug that is not there. The backend already separates them
 * (409 for no readings, 503 for a database problem), so the UI does too.
 */

import { AlertCircle, Inbox, RefreshCw } from 'lucide-react'

export function EmptyState({ title, description, icon: Icon = Inbox, action, className = '' }) {
  return (
    <div className={`glass flex flex-col items-center px-6 py-10 text-center ${className}`}>
      <Icon aria-hidden="true" className="h-8 w-8 text-ink-faint" />
      <h3 className="mt-3 text-sm font-semibold text-ink">{title}</h3>
      {description ? (
        <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-ink-muted">{description}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  )
}

export function ErrorState({ title = 'Something went wrong', description, onRetry, className = '' }) {
  return (
    <div
      className={`glass flex flex-col items-center px-6 py-10 text-center ${className}`}
      // Assertive: an error that replaces content the user asked for should interrupt,
      // unlike a passing notification.
      role="alert"
      aria-live="assertive"
    >
      <AlertCircle aria-hidden="true" className="h-8 w-8 text-danger" />
      <h3 className="mt-3 text-sm font-semibold text-ink">{title}</h3>
      {description ? (
        <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-ink-muted">{description}</p>
      ) : null}
      {onRetry ? (
        <button type="button" onClick={onRetry} className="btn-ghost mt-4">
          <RefreshCw aria-hidden="true" className="h-4 w-4" />
          Try again
        </button>
      ) : null}
    </div>
  )
}
