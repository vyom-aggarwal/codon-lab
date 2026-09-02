'use client'

import { scaleLinear } from 'd3-scale'

import type { Scorecard } from '@codonlab/schema'

/**
 * The calibration curve: mean measured against mean predicted, in equal-count bins.
 *
 * Read against the identity line. A well-calibrated predictor's bins sit on it;
 * a predictor with a constant offset sits on a line **parallel** to it — which
 * is exactly the failure ARCHITECTURE.md §13 says a rank statistic cannot see,
 * and this chart can. That is the whole reason it is on the screen.
 *
 * It renders only when the two series are commensurable, because a calibration
 * curve is a claim about absolute values and drawing one across two different
 * units would make the same error `domain/scorecard` refuses to make. When they
 * are not, the caller shows the reason instead of an empty frame.
 */

const WIDTH = 460
const HEIGHT = 300
const PAD = { top: 10, right: 12, bottom: 44, left: 56 }

export function CalibrationCurve({ card }: { card: Scorecard }) {
  const bins = card.calibration
  if (bins.length === 0) return null

  const innerWidth = WIDTH - PAD.left - PAD.right
  const innerHeight = HEIGHT - PAD.top - PAD.bottom

  // One shared domain for both axes so the identity line is a true 45°, which
  // is the only way "parallel to identity" is readable by eye.
  const values = bins.flatMap((bin) => [bin.predicted, bin.measured])
  const domain = scaleLinear()
    .domain([Math.min(...values), Math.max(...values)])
    .nice()
    .domain() as [number, number]

  const x = scaleLinear().domain(domain).range([0, innerWidth])
  const y = scaleLinear().domain(domain).range([innerHeight, 0])
  const ticks = x.ticks(6)

  const path = bins
    .map((bin, index) => `${index === 0 ? 'M' : 'L'}${x(bin.predicted)},${y(bin.measured)}`)
    .join(' ')

  const unit = card.error_unit ?? ''

  return (
    <figure className="m-0">
      <div className="w-full overflow-x-auto">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="w-full"
          role="img"
          aria-label={`Calibration curve, ${bins.length} bins, against the identity line`}
        >
          <g transform={`translate(${PAD.left},${PAD.top})`}>
            {ticks.map((tick) => (
              <g key={tick}>
                <line
                  x1={0}
                  x2={innerWidth}
                  y1={y(tick)}
                  y2={y(tick)}
                  className="stroke-border"
                  strokeWidth={1}
                />
                <line
                  y1={0}
                  y2={innerHeight}
                  x1={x(tick)}
                  x2={x(tick)}
                  className="stroke-border"
                  strokeWidth={1}
                />
                <text
                  x={-8}
                  y={y(tick)}
                  dy="0.32em"
                  textAnchor="end"
                  className="fill-text-muted text-11 tabular-nums"
                >
                  {format(tick)}
                </text>
                <text
                  x={x(tick)}
                  y={innerHeight + 16}
                  textAnchor="middle"
                  className="fill-text-muted text-11 tabular-nums"
                >
                  {format(tick)}
                </text>
              </g>
            ))}

            {/* Identity. Dashed so it reads as a reference, not as data. */}
            <line
              x1={x(domain[0])}
              y1={y(domain[0])}
              x2={x(domain[1])}
              y2={y(domain[1])}
              className="stroke-border-strong"
              strokeWidth={1}
              strokeDasharray="4 3"
            />
            <text
              x={innerWidth - 4}
              y={y(domain[1]) + 12}
              textAnchor="end"
              className="fill-text-muted text-11"
            >
              perfect calibration
            </text>

            <path d={path} fill="none" className="stroke-accent" strokeWidth={1.5} />
            {bins.map((bin, index) => (
              <circle
                key={index}
                cx={x(bin.predicted)}
                cy={y(bin.measured)}
                r={3}
                className="fill-accent"
              >
                <title>
                  {`Bin ${index + 1}: ${bin.count} variants, mean predicted ${format(
                    bin.predicted,
                  )} ${unit}, mean measured ${format(bin.measured)} ${unit}`}
                </title>
              </circle>
            ))}

            <line
              x1={0}
              y1={innerHeight}
              x2={innerWidth}
              y2={innerHeight}
              className="stroke-border-strong"
              strokeWidth={1}
            />
            <line
              x1={0}
              y1={0}
              x2={0}
              y2={innerHeight}
              className="stroke-border-strong"
              strokeWidth={1}
            />
          </g>

          <text
            x={PAD.left + innerWidth / 2}
            y={HEIGHT - 6}
            textAnchor="middle"
            className="fill-text-muted text-11"
          >
            {`Mean predicted${unit ? ` (${unit})` : ''}`}
          </text>
          <text
            transform={`translate(12,${PAD.top + innerHeight / 2}) rotate(-90)`}
            textAnchor="middle"
            className="fill-text-muted text-11"
          >
            {`Mean measured${unit ? ` (${unit})` : ''}`}
          </text>
        </svg>
      </div>
      <figcaption className="text-11 text-text-muted mt-1">
        Equal-count bins, so each rests on a similar number of variants; hover a point for its
        count. Bins parallel to the dashed line mean a constant offset — the error a rank
        statistic cannot see.
      </figcaption>
    </figure>
  )
}

function format(value: number): string {
  if (Math.abs(value) >= 100) return value.toFixed(0)
  if (Math.abs(value) >= 10) return value.toFixed(1)
  return value.toFixed(2)
}
