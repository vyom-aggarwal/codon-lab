import { FileUp } from 'lucide-react'
import type { Route } from 'next'
import Link from 'next/link'

import type { ScorecardReport } from '@codonlab/schema'

import { ScorecardCard } from './scorecard-card'

/**
 * The scorecard screen. Specification §5.9.
 *
 * The header states the one thing a reader must not get wrong about this
 * screen: a rank statistic answers "did it order them correctly", and nothing
 * more. ARCHITECTURE.md §13 requires the error and bias terms to travel with it,
 * and where they cannot be computed the reason is on the card rather than in a
 * footnote nobody reads.
 *
 * The empty states name the next action, per `BRIEF.md` §4, and they are
 * distinct: "no measurements yet" and "measurements but nothing has predicted
 * them" need different things done about them.
 */
export function ScorecardView({
  report,
  targetId,
  scope,
}: {
  report: ScorecardReport
  targetId?: string
  scope: string
}) {
  return (
    <div className="space-y-6 p-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-18 text-text">Predictor scorecard</h1>
          <p className="text-13 text-text-muted mt-1">
            {scope} · {report.measured_variants.toLocaleString()} variants with measured values
            {report.metrics.length > 0 ? ` · ${report.metrics.join(', ')}` : ''}
          </p>
        </div>
        {targetId ? (
          <Link
            href={`/targets/${targetId}/measurements` as Route}
            className="border-border rounded-control text-13 text-text hover:bg-surface-sunk h-control inline-flex items-center gap-1.5 border px-2"
          >
            <FileUp className="size-4" strokeWidth={1.5} />
            Import measured results
          </Link>
        ) : null}
      </header>

      {report.cards.length > 0 ? (
        <p className="border-border bg-surface-sunk rounded-panel text-12 text-text-muted border p-3">
          A rank statistic says whether a predictor ordered the variants correctly. It says
          nothing about whether the numbers are right: a predictor that reads a constant 2
          kcal/mol high scores a perfect ρ and a perfect precision@k. The error and bias figures
          sit beside the rank figures for that reason, and where they could not be computed the
          card says why instead of leaving a gap.
        </p>
      ) : null}

      {report.note ? (
        <div className="border-border bg-surface rounded-panel border p-6">
          <p className="text-13 text-text">{report.note}</p>
          {report.unjoined_measurements > 0 ? (
            <p className="text-12 text-text-muted mt-2">
              {report.unjoined_measurements.toLocaleString()} measured rows have not been matched
              to a variant. They are stored and can still be resolved by hand.
            </p>
          ) : null}
        </div>
      ) : null}

      {report.cards.map((card) => (
        <ScorecardCard key={`${card.model_version_id}-${card.measured_metric}`} card={card} />
      ))}

      {report.cards.length > 0 && report.unjoined_measurements > 0 ? (
        <p className="text-12 text-text-muted">
          {report.unjoined_measurements.toLocaleString()} measured rows across this lab are not
          matched to a variant and contribute to no card. They were kept, not discarded.
        </p>
      ) : null}
    </div>
  )
}
