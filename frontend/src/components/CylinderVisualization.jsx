/**
 * The hero: an LPG cylinder drawn to the level the sensor actually reports.
 *
 * Inline SVG rather than an image, because the fill height *is* the data - it is
 * `percentage` and nothing else, so the picture cannot disagree with the number printed
 * beside it.
 *
 * Accessibility: the whole figure is one `img`-role node with a text label, so a screen
 * reader hears "LPG level 58.5 percent, NORMAL, 8.308 kilograms remaining" instead of
 * trying to narrate a drawing. The numbers are also printed as text next to it, so the
 * visual is never the only way to read the level.
 */

import { StatusBadge } from './StatusBadge'

// Geometry of the cylinder body, in the SVG's own coordinate space.
const BODY_TOP = 46
const BODY_HEIGHT = 150
const BODY_LEFT = 28
const BODY_WIDTH = 84

const TONE = {
  NORMAL: { fill: '#34D399', glow: 'rgba(52,211,153,0.35)' },
  LOW: { fill: '#FBBF24', glow: 'rgba(251,191,36,0.35)' },
  CRITICAL: { fill: '#F87171', glow: 'rgba(248,113,113,0.4)' },
}

export function CylinderVisualization({
  percentage,
  remainingKg,
  capacityKg,
  status,
  isSimulated,
  className = '',
}) {
  const hasData = percentage !== null && percentage !== undefined
  // Clamped for drawing only. The printed number is whatever the API said.
  const clamped = hasData ? Math.min(100, Math.max(0, Number(percentage))) : 0
  const fillHeight = (clamped / 100) * BODY_HEIGHT
  const fillTop = BODY_TOP + (BODY_HEIGHT - fillHeight)
  const tone = TONE[status] ?? TONE.NORMAL

  const label = hasData
    ? `LPG level ${percentage} percent, ${status}, ${remainingKg} kilograms remaining of ${capacityKg} kilograms capacity`
    : 'No sensor readings recorded for this cylinder yet'

  return (
    <div className={`glass flex flex-col items-center gap-4 p-5 sm:flex-row sm:gap-6 ${className}`}>
      <svg
        viewBox="0 0 140 220"
        role="img"
        aria-label={label}
        className="h-44 w-auto shrink-0 sm:h-52"
      >
        <defs>
          <linearGradient id="lpg-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={tone.fill} stopOpacity="0.95" />
            <stop offset="100%" stopColor={tone.fill} stopOpacity="0.55" />
          </linearGradient>
          <clipPath id="lpg-body">
            <rect x={BODY_LEFT} y={BODY_TOP} width={BODY_WIDTH} height={BODY_HEIGHT} rx="18" />
          </clipPath>
        </defs>

        {/* Valve and collar */}
        <rect x="60" y="8" width="20" height="18" rx="4" fill="#64748B" />
        <rect x="52" y="24" width="36" height="12" rx="4" fill="#475569" />
        <rect x={BODY_LEFT + 10} y="34" width={BODY_WIDTH - 20} height="14" rx="6" fill="#334155" />

        {/* Body */}
        <rect
          x={BODY_LEFT}
          y={BODY_TOP}
          width={BODY_WIDTH}
          height={BODY_HEIGHT}
          rx="18"
          fill="#141F36"
          stroke="rgba(255,255,255,0.12)"
        />

        {/* The gas. Height is driven only by `percentage`. */}
        <g clipPath="url(#lpg-body)">
          <rect
            x={BODY_LEFT}
            y={fillTop}
            width={BODY_WIDTH}
            height={fillHeight}
            fill="url(#lpg-fill)"
            style={{ transition: 'y 700ms ease-out, height 700ms ease-out' }}
          />
          {/* Surface line, so the level is readable even at low fill. */}
          {clamped > 0 ? (
            <rect
              x={BODY_LEFT}
              y={fillTop}
              width={BODY_WIDTH}
              height="2"
              fill={tone.fill}
              style={{ transition: 'y 700ms ease-out' }}
            />
          ) : null}
        </g>

        {/* Base */}
        <rect x={BODY_LEFT + 6} y={BODY_TOP + BODY_HEIGHT - 4} width={BODY_WIDTH - 12} height="14" rx="4" fill="#334155" />

        {/* Percentage inside the cylinder. aria-hidden: the figure's label already
            carries it, and the same number is printed as text beside the drawing. */}
        <text
          x="70"
          y={BODY_TOP + BODY_HEIGHT / 2 + 6}
          textAnchor="middle"
          aria-hidden="true"
          className="fill-ink"
          style={{ fontSize: '22px', fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}
        >
          {hasData ? `${percentage}%` : '—'}
        </text>
      </svg>

      <div className="min-w-0 flex-1 text-center sm:text-left">
        <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">LPG remaining</p>
        <p className="tabular mt-1 flex items-baseline justify-center gap-1.5 sm:justify-start">
          <span className="text-4xl font-semibold text-ink">{hasData ? remainingKg : '—'}</span>
          <span className="text-base text-ink-muted">kg</span>
        </p>

        {hasData ? (
          <p className="tabular mt-1 text-sm text-ink-muted">
            of {capacityKg} kg capacity · {percentage}%
          </p>
        ) : (
          <p className="mt-1 text-sm text-ink-muted">Waiting for the first reading.</p>
        )}

        <div className="mt-3 flex flex-wrap items-center justify-center gap-2 sm:justify-start">
          {status ? <StatusBadge state={status} size="lg" /> : null}
          {isSimulated ? (
            <span
              className="rounded-full border border-demo/30 bg-demo-soft px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-demo"
              title="This reading was generated by the simulator, not measured by hardware"
            >
              Simulated reading
            </span>
          ) : null}
        </div>
      </div>
    </div>
  )
}
