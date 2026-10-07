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
import { ml, monitoring } from '../services/api'

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
  // What the model is actually worth. A user shown POWERED BY ML deserves to know what
  // that bought, and whether the model is even in use.
  const modelStatus = useResource(() => ml.status(), [])

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

      <ModelPanel status={modelStatus} />
    </div>
  )
}


/**
 * What the trained model measurably achieves - or why it is not being used.
 *
 * The error is shown against the error of simply predicting the historical mean, because
 * "MAE 0.03 kg/day" alone is unreadable and sounds impressive either way. A model that
 * loses to that average is reported as trained-but-idle rather than hidden: the backend
 * keeps serving the arithmetic estimate, and this panel says so.
 */
function ModelPanel({ status }) {
  if (status.loading || status.error || !status.data) return null

  const { trained, in_use: inUse, beats_baseline: beats, report, min_samples_required: minSamples } =
    status.data

  if (!trained) {
    return (
      <section aria-labelledby="model-heading" className="glass p-5">
        <h2 id="model-heading" className="text-sm font-semibold text-ink">
          Prediction model
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">
          No model has been trained yet, so every estimate is arithmetic. Training needs at least{' '}
          {minSamples} complete days of consumption.
        </p>
      </section>
    )
  }

  const improvement = report?.baseline_mae
    ? Math.round((1 - report.model_mae / report.baseline_mae) * 100)
    : null

  return (
    <section aria-labelledby="model-heading" className="glass p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="model-heading" className="text-sm font-semibold text-ink">
          Prediction model
        </h2>
        <span
          className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${
            inUse
              ? 'border-safe/30 bg-safe-soft text-safe'
              : 'border-hairline bg-surface-overlay/70 text-ink-muted'
          }`}
        >
          {inUse ? 'In use' : 'Trained, not used'}
        </span>
      </div>

      {inUse ? (
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">
          Trained on {report.sample_count} days. Across {report.folds}-fold cross-validation it is
          out by <span className="tabular font-semibold text-ink">{report.model_mae}</span> kg/day,
          against <span className="tabular font-semibold text-ink">{report.baseline_mae}</span> kg/day
          for simply predicting the historical average
          {improvement !== null ? <> — about {improvement}% better</> : null}.
        </p>
      ) : (
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">
          This model cross-validates <span className="tabular">{report.model_mae}</span> kg/day
          against <span className="tabular">{report.baseline_mae}</span> kg/day for the plain
          historical average, so the average is the better predictor and is what the estimate uses.
          Running a model is not by itself a reason to trust it.
        </p>
      )}

      {report?.feature_importances ? (
        <dl className="mt-4 space-y-1.5">
          {Object.entries(report.feature_importances)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 4)
            .map(([name, value]) => (
              <div key={name} className="flex items-center gap-3">
                <dt className="w-44 shrink-0 truncate text-[11px] text-ink-muted">
                  {name.replace(/_/g, ' ')}
                </dt>
                <dd className="flex min-w-0 flex-1 items-center gap-2">
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-overlay">
                    <span
                      className="block h-full rounded-full bg-accent"
                      style={{ width: `${Math.round(value * 100)}%` }}
                    />
                  </span>
                  <span className="tabular w-10 shrink-0 text-right text-[11px] text-ink-muted">
                    {Math.round(value * 100)}%
                  </span>
                </dd>
              </div>
            ))}
        </dl>
      ) : null}

      <p className="mt-3 text-[11px] leading-relaxed text-ink-faint">
        Cross-validated error on a short history of one household. It describes how well the model
        fits this data, not how accurately it would forecast a different home. Last trained{' '}
        {new Date(report.trained_at).toLocaleString()}.
      </p>
    </section>
  )
}
