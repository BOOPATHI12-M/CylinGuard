/**
 * The alert list.
 *
 * Grouped by severity rather than strictly by time, so a critical alert from yesterday is
 * not pushed below an informational one from this morning. Within a group it is newest
 * first.
 *
 * Mark-as-read updates the row in place from the server's response rather than guessing
 * locally: the unread count is recomputed server-side and the two must not disagree.
 */

import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { BellOff, Check, Loader2 } from 'lucide-react'

import { EmptyState, ErrorState } from '../components/EmptyState'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { StatusBadge } from '../components/StatusBadge'
import { useToast } from '../components/ToastNotification'
import { useResource } from '../hooks/useResource'
import { monitoring } from '../services/api'

// Worst first. A user scanning this page should meet the leak before the refill notice.
const SEVERITIES = [
  { id: 'CRITICAL', label: 'Critical', hint: 'Needs attention now' },
  { id: 'WARNING', label: 'Warnings', hint: 'Worth looking at' },
  { id: 'INFO', label: 'Information', hint: 'For the record' },
]

export function Alerts() {
  const { cylinderId } = useOutletContext()
  const toast = useToast()
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [marking, setMarking] = useState(null)

  const resource = useResource(
    () => monitoring.alerts(cylinderId, { unreadOnly, limit: 200 }),
    [cylinderId, unreadOnly],
    { enabled: Boolean(cylinderId) },
  )

  const markRead = async (alertId) => {
    setMarking(alertId)
    try {
      const updated = await monitoring.markAlertRead(alertId)
      resource.setData((current) =>
        current
          ? {
              ...current,
              unread_count: Math.max(0, current.unread_count - 1),
              items: current.items.map((item) => (item.id === updated.id ? updated : item)),
            }
          : current,
      )
    } catch (failure) {
      toast.warning(failure.message)
    } finally {
      setMarking(null)
    }
  }

  if (resource.loading && !resource.data) {
    return <LoadingSkeleton lines={8} label="Loading alerts" />
  }

  if (resource.error) {
    return (
      <ErrorState
        title="Alerts unavailable"
        description={resource.error.message}
        onRetry={resource.reload}
      />
    )
  }

  const { items, unread_count: unreadCount } = resource.data
  const grouped = SEVERITIES.map((severity) => ({
    ...severity,
    alerts: items.filter((item) => item.severity === severity.id),
  })).filter((group) => group.alerts.length > 0)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-muted" aria-live="polite">
          {unreadCount > 0 ? (
            <>
              <span className="tabular font-semibold text-ink">{unreadCount}</span> unread
            </>
          ) : (
            'Everything here has been read.'
          )}
        </p>

        <label className="flex items-center gap-2 text-xs text-ink-muted">
          <input
            type="checkbox"
            checked={unreadOnly}
            onChange={(event) => setUnreadOnly(event.target.checked)}
            className="h-4 w-4 rounded border-hairline bg-surface-raised text-accent"
          />
          Unread only
        </label>
      </div>

      {items.length === 0 ? (
        <EmptyState
          icon={BellOff}
          title={unreadOnly ? 'Nothing unread' : 'No alerts'}
          description={
            unreadOnly
              ? 'Every alert on this cylinder has been read.'
              : 'Nothing has needed your attention on this cylinder.'
          }
        />
      ) : (
        grouped.map((group) => (
          <section key={group.id} aria-labelledby={`group-${group.id}`} className="glass overflow-hidden">
            <div className="flex items-center justify-between gap-2 border-b border-hairline px-5 py-3">
              <div>
                <h2 id={`group-${group.id}`} className="flex items-center gap-2 text-sm font-semibold text-ink">
                  <StatusBadge state={group.id} size="sm" />
                  {group.label}
                </h2>
                <p className="mt-0.5 text-[11px] text-ink-faint">{group.hint}</p>
              </div>
              <span className="tabular text-xs text-ink-muted">{group.alerts.length}</span>
            </div>

            <ul className="divide-y divide-hairline/60">
              {group.alerts.map((alert) => (
                <li
                  key={alert.id}
                  className={`flex flex-col gap-2 px-5 py-3 sm:flex-row sm:items-start ${
                    alert.is_read ? '' : 'bg-surface-raised/30'
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm leading-relaxed text-ink">{alert.message}</p>
                    <p className="tabular mt-1 text-[11px] text-ink-faint">
                      {alert.type} · {new Date(alert.created_at).toLocaleString()}
                    </p>
                  </div>

                  {alert.is_read ? (
                    <span className="flex shrink-0 items-center gap-1 text-[11px] text-ink-faint">
                      <Check aria-hidden="true" className="h-3.5 w-3.5" />
                      Read
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => markRead(alert.id)}
                      disabled={marking === alert.id}
                      className="btn-ghost shrink-0 text-xs"
                    >
                      {marking === alert.id ? (
                        <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Check aria-hidden="true" className="h-3.5 w-3.5" />
                      )}
                      Mark read
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  )
}
