'use client'

import { scaleLinear } from 'd3-scale'
import { useId } from 'react'

import type { ScatterPoint } from '@codonlab/schema'

/**
 * Predicted against measured, per variant. Specification §5.9.
 *
 * D3 scales and plain SVG, per `BRIEF.md` §3 — no chart library. `scaleLinear`
 * earns its place for `.nice()` and `.ticks()`, which pick round axis values;
 * the rest is arithmetic that needed no dependency and still does not have one.
 *
 * Two decisions worth naming.
 *
 * **There is no trend line.** A fitted line through this cloud would read as a
 * claim about the relationship, and the statistic that claim rests on is
 * reported beside the chart with its caveats. Drawing it twice, once as a
 * number and once as an unlabelled line, is how a caveat gets lost.
 *
 * **The axes always state their units and sign conventions**, taken from the
 * card rather than written here, so the chart cannot disagree with the figures
 * next to it about which direction is better.
 */

const WIDTH = 460
const HEIGHT = 300
const PAD = { top: 10, right: 12, bottom: 44, left: 56 }

export function PredictedVsMeasured({
  points,
  predictedLabel,
  measuredLabel,
}: {
  points: ScatterPoint[]
  predictedLabel: string
  measuredLabel: string
}) {
  const clipId = useId()

  if (points.length === 0) {
    return (
      <p className="text-12 text-text-muted">
        No variant carries both a prediction and a measurement, so there is nothing to plot.
      </p>
    )
  }

  const innerWidth = WIDTH - PAD.left - PAD.right
  const innerHeight = HEIGHT - PAD.top - PAD.bottom

  const xValues = points.map((point) => point.predicted)
  const yValues = points.map((point) => point.measured)

  const x = scaleLinear()
    .domain([Math.min(...xValues), Math.max(...xValues)])
    .nice()
    .range([0, innerWidth])
  const y = scaleLinear()
    .domain([Math.min(...yValues), Math.max(...yValues)])
    .nice()
    .range([innerHeight, 0])

  const xTicks = x.ticks(6)
  const yTicks = y.ticks(6)

  return (
    <figure className="m-0">
      <div className="w-full overflow-x-auto">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="w-full"
          role="img"
          aria-label={`Predicted ${predictedLabel} against measured ${measuredLabel}, ${points.length} variants`}
        >
          <defs>
            <clipPath id={clipId}>
              <rect x={0} y={0} width={innerWidth} height={innerHeight} />
            </clipPath>
          </defs>

          <g transform={`translate(${PAD.left},${PAD.top})`}>
            {yTicks.map((tick) => (
              <g key={`y${tick}`} transform={`translate(0,${y(tick)})`}>
                <line x1={0} x2={innerWidth} className="stroke-border" strokeWidth={1} />
                <text
                  x={-8}
                  dy="0.32em"
                  textAnchor="end"
                  className="fill-text-muted text-11 tabular-nums"
                >
                  {format(tick)}
                </text>
              </g>
            ))}

            {xTicks.map((tick) => (
              <g key={`x${tick}`} transform={`translate(${x(tick)},0)`}>
                <line y1={0} y2={innerHeight} className="stroke-border" strokeWidth={1} />
                <text
                  y={innerHeight + 16}
                  textAnchor="middle"
                  className="fill-text-muted text-11 tabular-nums"
                >
                  {format(tick)}
                </text>
              </g>
            ))}

            <g clipPath={`url(#${clipId})`}>
              {points.map((point) => (
                <circle
                  key={point.code}
                  cx={x(point.predicted)}
                  cy={y(point.measured)}
                  r={2}
                  className="fill-accent"
                  fillOpacity={0.35}
                >
                  <title>
                    {`${point.code} — predicted ${format(point.predicted)}, measured ${format(
                      point.measured,
                    )}${point.replicates > 1 ? `, mean of ${point.replicates} replicates` : ''}`}
                  </title>
                </circle>
              ))}
            </g>

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
            {`Predicted — ${predictedLabel}`}
          </text>
          <text
            transform={`translate(12,${PAD.top + innerHeight / 2}) rotate(-90)`}
            textAnchor="middle"
            className="fill-text-muted text-11"
          >
            {`Measured — ${measuredLabel}`}
          </text>
        </svg>
      </div>
      <figcaption className="text-11 text-text-muted mt-1">
        One mark per variant, {points.length.toLocaleString()} in total. A variant measured more
        than once is plotted at the mean of its replicates.
      </figcaption>
    </figure>
  )
}

/** Enough digits to distinguish neighbouring ticks, no more. */
function format(value: number): string {
  if (Math.abs(value) >= 100) return value.toFixed(0)
  if (Math.abs(value) >= 10) return value.toFixed(1)
  return value.toFixed(2)
}
