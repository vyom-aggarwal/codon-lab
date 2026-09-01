'use client'

import type { RankedVariant, Ranking, Run, ScoreCell } from '@codonlab/schema'
import dynamic from 'next/dynamic'

import { DemoMark } from '@/components/run/demo-mark'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/cn'
import { rationaleFor } from '@/lib/rationale'

/**
 * The right pane: what this variant is, why it was proposed, and where every
 * number on it came from.
 *
 * DESIGN.md §2 — no modal for anything the user needs to reference while
 * working. Everything here stays open beside the table.
 */

// Mol* is multi-megabyte and needs WebGL. It must not reach the server bundle
// or the workbench's first paint.
const StructureViewer = dynamic(
  () => import('./structure-viewer').then((module) => module.StructureViewer),
  {
    ssr: false,
    loading: () => (
      <div className="border-border rounded-panel bg-surface-sunk aspect-square w-full border" />
    ),
  },
)

export function Inspector({
  variant,
  ranking,
  run,
  targetId,
  apiBase,
  onTrace,
  tracedCell,
}: {
  variant: RankedVariant | null
  ranking: Ranking
  run: Run
  targetId: string
  apiBase: string
  onTrace: (cell: ScoreCell) => void
  tracedCell: ScoreCell | null
}) {
  if (!variant) {
    return (
      <div className="flex h-full items-center p-4">
        <p className="text-13 text-text-muted">
          Select a variant to see why it was proposed and where its numbers came from.
        </p>
      </div>
    )
  }

  const clauses = rationaleFor(variant, ranking)

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <header className="border-border space-y-1 border-b p-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-15 font-strong font-mono">{variant.code}</h2>
          <span className="text-12 text-text-muted font-mono">{variant.hgvs}</span>
        </div>
        <p className="text-12 text-text-muted">{ranking.scheme_label}</p>
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          <Badge tone="neutral">rank {variant.rank}</Badge>
          {variant.features.region ? (
            <Badge tone="neutral">{variant.features.region}</Badge>
          ) : null}
          {variant.features.buried_by_ligand ? (
            <Badge tone="warn">buried when cofactor present</Badge>
          ) : null}
          {variant.filtered_by.map((kind) => (
            <Badge key={kind} tone="warn">
              removed: {kind.replace(/_/g, ' ')}
            </Badge>
          ))}
        </div>
      </header>

      <section className="border-border space-y-2 border-b p-4">
        <p className="text-11 text-text-muted font-medium uppercase tracking-wide">Scores</p>
        {variant.cells.length === 0 ? (
          <p className="text-12 text-text-muted">No predictor produced a value here.</p>
        ) : (
          <ul className="divide-border divide-y">
            {variant.cells.map((cell) => {
              const metric = ranking.metrics.find((candidate) => candidate.id === cell.metric)
              const traced = tracedCell?.model_version_id === cell.model_version_id
              return (
                <li key={cell.metric} className="flex items-baseline gap-2 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-12 text-text-muted">{metric?.label ?? cell.metric}</p>
                    <p className="text-13 tabular-nums">
                      {cell.value.toFixed(2)}
                      {metric?.reports_interval && cell.uncertainty !== null
                        ? ` ± ${cell.uncertainty.toFixed(2)}`
                        : ''}
                      {metric?.unit ? ` ${metric.unit}` : ''}
                      {cell.is_mock ? <DemoMark modelName={cell.model_id} /> : null}
                    </p>
                    <p className="text-11 text-text-faint">{metric?.sign_convention}</p>
                  </div>
                  {/* Click two of the whole flow: row, then this. */}
                  <Button
                    size="sm"
                    variant={traced ? 'primary' : 'default'}
                    onClick={() => onTrace(cell)}
                  >
                    Trace
                  </Button>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <section className="border-border space-y-2 border-b p-4">
        <p className="text-11 text-text-muted font-medium uppercase tracking-wide">
          Why this was proposed
        </p>
        {/* Composed from the values on the row — never from a language model.
            Each clause names the field it rests on so it can be checked. */}
        <ul className="space-y-2">
          {clauses.map((clause) => (
            <li key={`${clause.source}:${clause.text}`} className="flex gap-2">
              <span
                className={cn(
                  'text-11 mt-0.5 w-20 shrink-0 uppercase tracking-wide',
                  clause.caution ? 'text-warn' : 'text-text-faint',
                )}
              >
                {clause.source}
              </span>
              <span className="text-12 text-text-muted min-w-0">{clause.text}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="p-4">
        <StructureViewer
          targetId={targetId}
          apiBase={apiBase}
          authorLabel={variant.features.author_label}
          code={variant.code}
        />
      </section>

      <section className="border-border border-t p-4">
        <p className="text-11 text-text-muted font-medium uppercase tracking-wide">Run</p>
        <p className="text-12 text-text-muted mt-1 font-mono">{run.id.slice(0, 8)}</p>
      </section>
    </div>
  )
}
