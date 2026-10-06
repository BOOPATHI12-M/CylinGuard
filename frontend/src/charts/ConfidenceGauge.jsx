/**
 * The prediction confidence dial.
 *
 * A plain SVG arc rather than a Recharts RadialBar: it is one value, and a chart library
 * brings an axis, a legend and a tooltip that all have to be switched off again.
 *
 * The number is printed in the middle *and* carried in the aria-label, so the arc is
 * decoration rather than the only way to read the value. A low-confidence estimate is
 * drawn in the muted tone - the dial should not look reassuring when the figure is not.
 */

const SIZE = 132
const STROKE = 10
const RADIUS = (SIZE - STROKE) / 2
// Three-quarter dial: the gap at the bottom is what reads as a gauge rather than a
// pie, and it leaves room for the caption.
const SWEEP = 0.75
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

export function ConfidenceGauge({ confidence, method, label = 'Prediction confidence' }) {
  const value = Math.min(1, Math.max(0, Number(confidence ?? 0)))
  const percent = Math.round(value * 100)

  // The arithmetic fallback caps around 0.55, so anything under ~0.4 is thin history or
  // a volatile household - shown muted so the dial does not overstate the number.
  const tone = method === 'ML' ? '#34D399' : value >= 0.4 ? '#38BDF8' : '#9BABC7'

  const dash = CIRCUMFERENCE * SWEEP
  const filled = dash * value

  return (
    <div className="flex flex-col items-center">
      <svg
        width={SIZE}
        height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        role="img"
        aria-label={`${label}: ${percent} percent, from ${method === 'ML' ? 'the trained model' : 'an arithmetic estimate'}`}
      >
        {/* Rotated so the gap sits at the bottom. */}
        <g transform={`rotate(135 ${SIZE / 2} ${SIZE / 2})`}>
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke="rgba(255,255,255,0.08)"
            strokeWidth={STROKE}
            strokeDasharray={`${dash} ${CIRCUMFERENCE}`}
            strokeLinecap="round"
          />
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke={tone}
            strokeWidth={STROKE}
            strokeDasharray={`${filled} ${CIRCUMFERENCE}`}
            strokeLinecap="round"
            style={{ transition: 'stroke-dasharray 700ms ease-out' }}
          />
        </g>
        <text
          x={SIZE / 2}
          y={SIZE / 2 + 2}
          textAnchor="middle"
          aria-hidden="true"
          className="fill-ink"
          style={{ fontSize: '26px', fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}
        >
          {percent}%
        </text>
        <text
          x={SIZE / 2}
          y={SIZE / 2 + 22}
          textAnchor="middle"
          aria-hidden="true"
          className="fill-ink-muted"
          style={{ fontSize: '10px', letterSpacing: '0.08em' }}
        >
          CONFIDENCE
        </text>
      </svg>
    </div>
  )
}
