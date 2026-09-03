'use client'

import type { Scorecard } from '@codonlab/schema'
import { Badge } from '@/components/ui'

import { CalibrationCurve } from './calibration'
import { PredictedVsMeasured } from './scatter'

/**
 * One predictor's record against one set of measurements.
 *
 * **This component's shape is a contract, not a layout preference.**
 * ARCHITECTURE.md §13: "The bias term is rendered visually adjacent to the rank
 * term, not in a detail panel or behind a tab. A predictor that ranks perfectly
 * and sits 2 kcal/mol high must show both facts in one glance, or the scorecard
 * has failed at the only job it has."
 *
 * So the four figures live in **one row, in one grid, in this order**: Spearman,
 * precision@k, MAE, mean signed error. Rank and bias are two cells apart and
 * cannot be separated by a tab, a disclosure or a scroll. `scorecard.test.tsx`
 * asserts the adjacency directly rather than trusting this comment.
 *
 * When the error terms cannot be computed — different units, or opposed sign
 * conventions — the cells read `—` and the reason is printed **inside the same
 * block**, immediately beneath. A reader must never be able to mistake "we could
 * not measure the error" for "the error is small".
 */
export function ScorecardCard({ card }: { card: Scorecard }) {
  const rankOnly = card.mae === null

  return (
    <article
      className="border-border bg-surface rounded-panel border p-4"
      aria-label={`Scorecard for ${card.model_name}`}
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <h3 className="text-15 font-strong text-text">{card.model_name}</h3>
          <span className="text-12 text-text-muted font-mono">{card.model_version}</span>
          {card.is_mock ? (
            <Badge tone="warn">Synthetic predictor — not model output</Badge>
          ) : null}
        </div>
        <p className="text-12 text-text-muted tabular-nums">
          {card.n.toLocaleString()} variants with both a prediction and a measurement
        </p>
      </header>

      <p className="text-12 text-text-muted mt-1">
        Predicted <span className="text-text">{card.predicted_metric}</span> in{' '}
        {card.predicted_unit} ({card.predicted_sign}) against measured{' '}
        <span className="text-text">{card.measured_metric}</span> in {card.measured_unit} (
        {card.measured_sign}).
      </p>

      {/* The one row §13 requires. Rank, rank, error, bias — in that order. */}
      <dl className="border-border mt-4 grid grid-cols-2 gap-px border sm:grid-cols-4">
        <Figure
          term="Spearman ρ"
          value={card.spearman === null ? null : card.spearman.toFixed(3)}
          note="Rank. +1 means it agrees with the bench about which variants are better."
          absent="Undefined — fewer than two variants vary."
        />
        <Figure
          term={`Precision@${card.precision_k}`}
          value={card.precision === null ? null : card.precision.toFixed(2)}
          note={`Rank. Of its best ${card.precision_k}, the share the bench also ranked in the top ${card.precision_k}.`}
          absent={card.precision_note}
        />
        <Figure
          term={`MAE${card.error_unit ? ` (${card.error_unit})` : ''}`}
          value={card.mae === null ? null : card.mae.toFixed(2)}
          note="Error. How far off it is, in absolute terms."
          absent="Not computable — see below."
        />
        <Figure
          term={`Mean signed error${card.error_unit ? ` (${card.error_unit})` : ''}`}
          value={
            card.mean_signed_error === null ? null : signed(card.mean_signed_error)
          }
          note={card.bias_note || 'Bias. Whether it is off in one direction.'}
          absent="Not computable — see below."
          emphasise
        />
      </dl>

      {rankOnly ? (
        <p className="border-warn/30 bg-warn/8 rounded-panel text-12 text-text mt-2 border p-3">
          <span className="font-strong">No error or bias figure for this pair. </span>
          {card.error_unavailable_reason} A rank statistic on its own says only whether the
          ordering is right, not whether the numbers are.
        </p>
      ) : null}

      <div className="mt-4 grid gap-6 lg:grid-cols-2">
        <div>
          <h4 className="text-13 font-strong text-text mb-1">Predicted against measured</h4>
          <PredictedVsMeasured
            points={card.points}
            predictedLabel={`${card.predicted_metric} (${card.predicted_unit})`}
            measuredLabel={`${card.measured_metric} (${card.measured_unit})`}
          />
        </div>
        <div>
          <h4 className="text-13 font-strong text-text mb-1">Calibration</h4>
          {card.calibration.length > 0 ? (
            <CalibrationCurve card={card} />
          ) : (
            <p className="text-12 text-text-muted">
              A calibration curve compares absolute values, so it needs the two series to be in
              the same unit and the same sign convention. {card.error_unavailable_reason}
            </p>
          )}
        </div>
      </div>

      <footer className="border-border text-11 text-text-muted mt-4 border-t pt-2">
        <span className="text-text-muted">Weights </span>
        <span className="text-text font-mono">{card.weights_hash.slice(0, 16)}…</span>
        {card.targets.length > 0 ? (
          <>
            <span className="text-text-muted">
              {' · '}
              {card.target_count === 1 ? 'Target ' : `${card.target_count} targets `}
            </span>
            {/* The count comes from distinct target rows, the names from their
                labels. They disagree whenever several targets share a name,
                which repeated runs make common — and saying "Target Lipase
                EstA" over eight pooled targets would misstate what the figures
                above rest on. */}
            <span className="text-text">{card.targets.join(', ')}</span>
          </>
        ) : null}
      </footer>
    </article>
  )
}

/**
 * One figure. `—` with its reason when absent — never a zero, never a blank.
 *
 * `emphasise` marks the bias cell. It shares the row with the rank figures
 * deliberately: the point of §13 is that the two are read together.
 */
function Figure({
  term,
  value,
  note,
  absent,
  emphasise = false,
}: {
  term: string
  value: string | null
  note: string
  absent: string
  emphasise?: boolean
}) {
  return (
    <div className="bg-surface p-3">
      <dt className="text-11 text-text-muted uppercase">{term}</dt>
      <dd className="mt-0.5">
        {value === null ? (
          <span className="text-15 text-text-muted tabular-nums" title={absent}>
            —
          </span>
        ) : (
          <span
            className={
              emphasise
                ? 'text-18 text-text font-strong tabular-nums'
                : 'text-18 text-text tabular-nums'
            }
          >
            {value}
          </span>
        )}
      </dd>
      <p className="text-11 text-text-muted mt-1">{value === null ? absent : note}</p>
    </div>
  )
}

/** A bias figure with no sign is unreadable, so the plus is always drawn. */
function signed(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`
}
