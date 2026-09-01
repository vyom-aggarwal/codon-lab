import type { Ranking, ScoreCell } from '@codonlab/schema'

import {
  EmptyCell,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from '@/components/ui/table'

import { DemoFootnote, DemoMark } from './demo-mark'

/**
 * The run's result, as far as Phase 4 goes: enough of the ranking to show that
 * the run completed and that every number on it is attributable. The full
 * virtualised workbench is Phase 5.
 *
 * Three rules from the specification are visible here.
 *
 * * Units and sign conventions live in the column header, and come from the
 *   provider's own declaration rather than from a string written in this file.
 * * A number a mock produced carries a mark. Every one of them, individually.
 * * A missing number is an em dash with the reason on hover — never a zero,
 *   never a blank, never an imputed value.
 */

function formatValue(cell: ScoreCell, reportsInterval: boolean): string {
  const value = cell.value.toFixed(2)
  if (!reportsInterval || cell.uncertainty === null) return value
  return `${value} ± ${cell.uncertainty.toFixed(2)}`
}

function describeCell(cell: ScoreCell, reportsInterval: boolean): string {
  if (reportsInterval && cell.ci_low !== null && cell.ci_high !== null) {
    return `95% interval ${cell.ci_low.toFixed(2)} to ${cell.ci_high.toFixed(2)}, from ${cell.model_id}.`
  }
  return `${cell.model_id} reports this metric as a point estimate; it has no interval, and none was invented.`
}

export function RankedTable({ ranking }: { ranking: Ranking }) {
  const anyMock = ranking.rows.some((row) => row.cells.some((cell) => cell.is_mock))

  return (
    <div className="space-y-3">
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell numeric className="w-12">
              Rank
            </TableHeaderCell>
            <TableHeaderCell>
              <span className="block">Mutation</span>
              <span className="text-text-muted block normal-case">{ranking.scheme_label}</span>
            </TableHeaderCell>
            {ranking.metrics.map((metric) => (
              <TableHeaderCell key={metric.id} numeric>
                <span className="block">{metric.label}</span>
                <span className="text-text-muted block normal-case">
                  {[metric.unit, metric.sign_convention].filter(Boolean).join(' · ')}
                </span>
              </TableHeaderCell>
            ))}
            <TableHeaderCell numeric>
              <span className="block">Consensus</span>
              <span className="text-text-muted block normal-case">mean rank, 1 best</span>
            </TableHeaderCell>
            <TableHeaderCell numeric>
              <span className="block">Disagreement</span>
              <span className="text-text-muted block normal-case">rank spread</span>
            </TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {ranking.rows.map((row) => (
            <TableRow key={row.code}>
              <TableCell numeric muted>
                {row.rank}
              </TableCell>
              <TableCell mono>
                {row.code}{' '}
                <span className="text-text-muted">({row.hgvs})</span>
              </TableCell>

              {ranking.metrics.map((metric) => {
                const cell = row.cells.find((candidate) => candidate.metric === metric.id)
                if (!cell) {
                  return (
                    <TableCell key={metric.id} numeric>
                      <EmptyCell
                        reason={
                          ranking.unavailable[metric.id] ??
                          'No predictor produced this metric for this variant.'
                        }
                      />
                    </TableCell>
                  )
                }
                return (
                  <TableCell key={metric.id} numeric>
                    <span title={describeCell(cell, metric.reports_interval)}>
                      {formatValue(cell, metric.reports_interval)}
                    </span>
                    {cell.is_mock ? <DemoMark modelName={cell.model_id} /> : null}
                  </TableCell>
                )
              })}

              <TableCell numeric>{row.consensus.toFixed(3)}</TableCell>
              <TableCell numeric>
                {row.disagreement === null ? (
                  <EmptyCell reason="Only one predictor scored this variant, so there is nothing to disagree about. Zero would read as unanimity." />
                ) : (
                  <span
                    title={`${row.sources_scored} predictors scored this variant. 0 is identical ranking, 1 is opposite.`}
                  >
                    {/* Three decimals, matching consensus: at two, a real spread
                        of 0.001 rounds to 0.00 and reads as unanimity. */}
                    {row.disagreement.toFixed(3)}
                  </span>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <div className="space-y-1">
        <p className="text-12 text-text-muted">
          Consensus is the mean of each predictor&rsquo;s normalised rank, not a physical quantity.
          Values are ranked within each predictor before combining, because a ΔΔG in kcal/mol and a
          log-likelihood ratio are not on the same scale.
        </p>
        {anyMock ? <DemoFootnote /> : null}
      </div>
    </div>
  )
}
