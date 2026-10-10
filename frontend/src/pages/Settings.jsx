/**
 * The ten per-cylinder tunables, plus demo controls and the alert-sound opt-in.
 *
 * This page is the whole of what the UI is allowed to write, and it deliberately exposes
 * nothing secret: the `settings` table holds thresholds and intervals only. The JWT
 * secret, the database password and the device key live in `.env` and are not reachable
 * from here - the backend's update model ignores unknown fields, so even a crafted
 * request cannot reach them.
 *
 * Every input is bounded to mirror the CHECK constraints in `database/schema.sql`, so a
 * bad value is a readable message rather than an opaque database error.
 */

import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { Loader2, RotateCcw, Save, Volume2 } from 'lucide-react'

import { EmptyState, ErrorState } from '../components/EmptyState'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { useToast } from '../components/ToastNotification'
import { useAlertSound } from '../hooks/useAlertSound'
import { useResource } from '../hooks/useResource'
import { demo as demoApi, monitoring } from '../services/api'

const FIELDS = [
  {
    key: 'low_lpg_threshold',
    label: 'Low LPG warning',
    unit: '% of capacity',
    min: 1,
    max: 100,
    step: 1,
    help: 'A warning alert is raised when the level falls to or below this.',
  },
  {
    key: 'critical_lpg_threshold',
    label: 'Critical LPG warning',
    unit: '% of capacity',
    min: 1,
    max: 100,
    step: 1,
    help: 'Must be at or below the low threshold — it is the more urgent of the two.',
  },
  {
    key: 'gas_leakage_threshold',
    label: 'Gas alarm threshold',
    unit: 'raw MQ-6 value',
    min: 1,
    max: 4095,
    step: 10,
    help: 'A raw ADC reading, not a concentration. Clean air sits near 180.',
  },
  {
    key: 'anomaly_threshold',
    label: 'Abnormal consumption',
    unit: '% above average',
    min: 1,
    max: 999,
    step: 5,
    help: 'High use alone is never treated as a leak — that needs the gas sensor to agree.',
  },
  {
    key: 'measurement_interval',
    label: 'Reporting interval',
    unit: 'seconds',
    // The range the firmware will honour. Offering a value the device ignores would
    // leave this page claiming one rate while the device reports at another.
    min: 5,
    max: 3600,
    step: 5,
    help: 'How often the device reports. The device picks this up on its next report. Leak detection latency is bounded by it, so shorter is safer.',
  },
  {
    key: 'prediction_threshold',
    label: 'Refill reminder',
    unit: 'days remaining',
    min: 0,
    max: 365,
    step: 1,
    help: 'The refill card starts recommending a refill at or below this many days left.',
  },
]

export function Settings() {
  const { cylinderId } = useOutletContext()
  const toast = useToast()
  const sound = useAlertSound()

  const [draft, setDraft] = useState(null)
  const [saving, setSaving] = useState(false)

  const settings = useResource(
    () => monitoring.settings(cylinderId),
    [cylinderId],
    { enabled: Boolean(cylinderId) },
  )
  const demoState = useResource(
    () => demoApi.state(cylinderId),
    [cylinderId],
    { enabled: Boolean(cylinderId) },
  )

  useEffect(() => {
    if (settings.data) setDraft(settings.data)
  }, [settings.data])

  const dirty =
    draft && settings.data && FIELDS.some((field) => draft[field.key] !== settings.data[field.key])

  const save = async () => {
    setSaving(true)
    try {
      const patch = {}
      for (const field of FIELDS) {
        if (draft[field.key] !== settings.data[field.key]) patch[field.key] = Number(draft[field.key])
      }
      const updated = await monitoring.updateSettings(cylinderId, patch)
      settings.setData(updated)
      setDraft(updated)
      toast.success('Settings saved.')
    } catch (failure) {
      // The backend rejects critical > low with an explanatory message; surface it
      // verbatim rather than inventing a generic one.
      toast.warning(failure.message)
    } finally {
      setSaving(false)
    }
  }

  const toggleDemo = async (enabled) => {
    try {
      const next = await demoApi.toggle(cylinderId, enabled)
      demoState.setData(next)
      toast.info(enabled ? 'Demo mode on.' : 'Demo mode off.')
    } catch (failure) {
      toast.warning(failure.message)
    }
  }

  const chooseScenario = async (scenario) => {
    try {
      const next = await demoApi.scenario(cylinderId, scenario)
      demoState.setData(next)
      toast.info(`Scenario set to ${scenario.replace('_', ' ').toLowerCase()}.`)
    } catch (failure) {
      toast.warning(failure.message)
    }
  }

  if (settings.loading && !draft) return <LoadingSkeleton lines={10} label="Loading settings" />

  if (!draft) {
    if (settings.error?.status === 404) {
      return (
        <EmptyState
          title="No settings for this cylinder"
          description="A settings row is created with the cylinder during setup."
        />
      )
    }
    return (
      <ErrorState
        title="Settings unavailable"
        description={settings.error?.message ?? 'Could not load the settings.'}
        onRetry={settings.reload}
      />
    )
  }

  return (
    <div className="space-y-5">
      <section aria-labelledby="thresholds-heading" className="glass p-5">
        <h2 id="thresholds-heading" className="text-sm font-semibold text-ink">
          Thresholds and intervals
        </h2>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {FIELDS.map((field) => (
            <div key={field.key}>
              <label htmlFor={field.key} className="label">
                {field.label}
              </label>
              <div className="flex items-center gap-2">
                <input
                  id={field.key}
                  type="number"
                  inputMode="numeric"
                  min={field.min}
                  max={field.max}
                  step={field.step}
                  value={draft[field.key]}
                  onChange={(event) =>
                    setDraft({ ...draft, [field.key]: event.target.value })
                  }
                  aria-describedby={`${field.key}-help`}
                  className="field tabular"
                />
                <span className="shrink-0 text-xs text-ink-muted">{field.unit}</span>
              </div>
              <p id={`${field.key}-help`} className="mt-1 text-[11px] leading-relaxed text-ink-faint">
                {field.help}
              </p>
            </div>
          ))}
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2">
          <button type="button" onClick={save} disabled={!dirty || saving} className="btn-primary text-sm">
            {saving ? (
              <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
            ) : (
              <Save aria-hidden="true" className="h-4 w-4" />
            )}
            Save changes
          </button>
          {dirty ? (
            <button
              type="button"
              onClick={() => setDraft(settings.data)}
              className="btn-ghost text-sm"
            >
              <RotateCcw aria-hidden="true" className="h-4 w-4" />
              Discard
            </button>
          ) : null}
          <p className="text-[11px] text-ink-faint" aria-live="polite">
            {dirty ? 'Unsaved changes' : 'Saved'}
          </p>
        </div>
      </section>

      <section aria-labelledby="demo-heading" className="glass p-5">
        <h2 id="demo-heading" className="text-sm font-semibold text-ink">
          Demo mode
        </h2>
        <p className="mt-1 text-sm leading-relaxed text-ink-muted">
          Generates plausible readings so the dashboard can be shown without hardware. Any genuine
          packet from a real device suspends it for this cylinder.
        </p>

        {demoState.loading ? (
          <LoadingSkeleton lines={2} className="mt-4" label="Loading demo state" />
        ) : demoState.error ? (
          <ErrorState
            className="mt-4"
            title="Demo state unavailable"
            description={demoState.error.message}
            onRetry={demoState.reload}
          />
        ) : (
          <>
            <label className="mt-4 flex items-center gap-2.5 text-sm text-ink">
              <input
                type="checkbox"
                checked={demoState.data.demo_mode}
                onChange={(event) => toggleDemo(event.target.checked)}
                className="h-4 w-4 rounded border-hairline bg-surface-raised text-accent"
              />
              Demo mode enabled for this cylinder
            </label>

            <fieldset className="mt-4" disabled={!demoState.data.demo_mode}>
              <legend className="label">Scenario</legend>
              <div className="flex flex-wrap gap-2">
                {demoState.data.available_scenarios.map((scenario) => (
                  <button
                    key={scenario}
                    type="button"
                    onClick={() => chooseScenario(scenario)}
                    aria-pressed={demoState.data.scenario === scenario}
                    className={`rounded-xl2 border px-3 py-2 text-xs font-medium transition-colors disabled:opacity-50 ${
                      demoState.data.scenario === scenario
                        ? 'border-accent/40 bg-accent-soft text-accent'
                        : 'border-hairline text-ink-muted hover:text-ink'
                    }`}
                  >
                    {scenario.replace(/_/g, ' ')}
                  </button>
                ))}
              </div>
            </fieldset>

            <dl className="mt-4 space-y-1.5 text-xs">
              <div className="flex justify-between gap-2">
                <dt className="text-ink-faint">Simulator loop running</dt>
                <dd className="text-ink-muted">
                  {demoState.data.simulator_running ? 'yes' : 'no — DEMO_SIMULATOR_ENABLED is off'}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-ink-faint">Suspended by a real device</dt>
                <dd className="text-ink-muted">
                  {demoState.data.suspended_by_real_device ? 'yes' : 'no'}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-ink-faint">Readings generated</dt>
                <dd className="tabular text-ink-muted">{demoState.data.ticks_generated}</dd>
              </div>
            </dl>
          </>
        )}
      </section>

      <section aria-labelledby="sound-heading" className="glass p-5">
        <h2 id="sound-heading" className="flex items-center gap-2 text-sm font-semibold text-ink">
          <Volume2 aria-hidden="true" className="h-4 w-4 text-ink-faint" />
          Critical alert sound
        </h2>

        {sound.isSupported ? (
          <>
            <label className="mt-3 flex items-center gap-2.5 text-sm text-ink">
              <input
                type="checkbox"
                checked={sound.enabled}
                onChange={(event) => sound.setPreference(event.target.checked)}
                className="h-4 w-4 rounded border-hairline bg-surface-raised text-accent"
              />
              Play a sound when a gas alarm starts
            </label>
            {sound.enabled ? (
              <button type="button" onClick={sound.play} className="btn-ghost mt-3 text-xs">
                Test the sound
              </button>
            ) : null}
            <p className="mt-3 text-[11px] leading-relaxed text-ink-faint">
              Off by default, and set here rather than automatically: browsers block audio until
              you have interacted with the page, so an alarm that armed itself would fail silently.
              It sounds once when an alarm starts, not on every reading. The banner, the colour and
              the words all work without it.
            </p>
          </>
        ) : (
          <p className="mt-3 text-sm text-ink-muted">
            This browser does not support the Web Audio API, so the alert sound is unavailable.
          </p>
        )}
      </section>

      <p className="text-[11px] leading-relaxed text-ink-faint">
        These are the only values this page can change. Credentials — the database password, the
        JWT secret and the device key — live in the server's environment file and are never sent to
        the browser.
      </p>
    </div>
  )
}
