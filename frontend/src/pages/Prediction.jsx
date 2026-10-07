/**
 * When the cylinder runs out, and how much to trust that.
 *
 * The page is built around the honesty rule rather than the number: the badge is driven
 * by `method`, the confidence is shown as a figure rather than described in words, and
 * the explanation says plainly which calculation produced the answer. A prediction page
 * that looks authoritative while running on division would be the easiest place in the
 * product to mislead someone.
 */

import { useOutletContext } from 'react-router-dom'
import { CalendarClock, Clock, Database, TrendingDown } from 'lucide-react'

import { ConfidenceGauge } from '../charts/ConfidenceGauge'
import { EmptyState, ErrorState } from '../components/EmptyState'
import { CardSkeleton } from '../components/LoadingSkeleton'
import { MetricCard } from '../components/MetricCard'
import { EstimateBadge } from '../components/StatusBadge'
import { useResource } from '../hooks/useResource'
import { monitoring } from '../services/api'

// Matches ML_MIN_SAMPLES in backend/app/config.py. Shown so the page can explain why
// it is still an estimate rather than leaving the user to guess.
const ML_MIN_SAMPLES = 14

export function Prediction() {
  const { cylinderId, frame } = useOutletContext()

  const resource = useResource(
    () => monitoring.prediction(cylinderId),
    [cylinderId],
    { enabled: Boolean(cylinderId) },
  )

  // A live frame carries the same prediction, so the page keeps up without refetching.
  const prediction = frame?.prediction ?? resource.data

  if (resource.loading && !prediction) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
    )
  }

  if (!prediction) {
    if (resource.error?.status === 404) {
      return (
        <EmptyState
          icon={TrendingDown}
          title="No prediction yet"
          description="A prediction is computed once the first reading arrives and at least one day of consumption has been recorded."
        />
      )
    }
    return (
      <ErrorState
        title="Prediction unavailable"
        description={resource.error?.message ?? 'The prediction could not be loaded.'}
        onRetry={resource.reload}
      />
    )
  }

  const usingModel = prediction.method === 'ML'
  const shortOfSamples = prediction.sample_count < ML_MIN_SAMPLES

  return (
    <div className="space-y-5">
      <section aria-labelledby="prediction-heading" className="glass p-5">
        <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-start">
          <ConfidenceGauge confidence={prediction.confidence} method={prediction.method} />

          <div className="min-w-0 flex-1 text-center sm:text-left">
            <div className="flex flex-wrap items-center justify-center gap-2 sm:justify-start">
              <h2 id="prediction-heading" className="text-sm font-semibold text-ink">
                Depletion estimate
              </h2>
              <EstimateBadge isEstimate={prediction.is_estimate} />
            </div>

            <p className="tabular mt-2 flex items-baseline justify-center gap-1.5 sm:justify-start">
              <span className="text-4xl font-semibold text-ink">{prediction.remaining_days}</span>
              <span className="text-base text-ink-muted">days remaining</span>
            </p>

            {prediction.predicted_depletion_date ? (
              <p className="tabular mt-1 flex items-center justify-center gap-1.5 text-sm text-ink-muted sm:justify-start">
                <CalendarClock aria-hidden="true" className="h-4 w-4" />
                Estimated to run out on{' '}
                <span className="font-medium text-ink">{prediction.predicted_depletion_date}</span>
              </p>
            ) : (
              <p className="mt-1 text-sm text-ink-muted">
                No depletion date: consumption is too low to project from.
              </p>
            )}
          </div>
        </div>
      </section>

      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard
          label="Remaining at estimate"
          value={prediction.remaining_kg}
          unit="kg"
          icon={TrendingDown}
        />
        <MetricCard
          label="History used"
          value={prediction.sample_count}
          unit="days"
          icon={Database}
          hint={shortOfSamples ? `Model needs ${ML_MIN_SAMPLES}` : 'Enough for the model'}
        />
        <MetricCard
          label="Computed"
          value={new Date(prediction.timestamp).toLocaleTimeString()}
          icon={Clock}
          hint={new Date(prediction.timestamp).toLocaleDateString()}
        />
      </div>

      <section aria-labelledby="how-heading" className="glass p-5">
        <h2 id="how-heading" className="text-sm font-semibold text-ink">
          How this was calculated
        </h2>

        {usingModel ? (
          <p className="mt-2 text-sm leading-relaxed text-ink-muted">
            A trained model produced this figure from {prediction.sample_count} days of recorded
            consumption, using the current level, the daily averages over 7 and 30 days, recent
            use, how much that use varies, and the day of the week.
          </p>
        ) : (
          <>
            <p className="mt-2 text-sm leading-relaxed text-ink-muted">
              This is arithmetic, not a model: the gas remaining divided by the average daily
              consumption.
            </p>
            <p className="tabular mt-2 rounded-xl2 border border-hairline bg-surface-overlay/60 px-3 py-2 font-mono text-xs text-ink">
              {prediction.remaining_kg} kg ÷ daily average = {prediction.remaining_days} days
            </p>
            <p className="mt-2 text-sm leading-relaxed text-ink-muted">
              {shortOfSamples
                ? `Below ${ML_MIN_SAMPLES} days of history the model is skipped deliberately — there is not enough to learn a pattern from, and a confident-looking number would be worse than an honest rough one.`
                : 'The model is not trained yet, so the arithmetic path is still in use.'}
            </p>
          </>
        )}

        <p className="mt-3 text-[11px] leading-relaxed text-ink-faint">
          Confidence is derived from how many days of history exist and how steady they are —
          it is not a probability that the date is correct. A household whose daily use swings
          widely is genuinely less predictable, and the figure reflects that. Treat the date as
          a planning aid, not a guarantee.
        </p>
      </section>
    </div>
  )
}
