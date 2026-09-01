import type { RunDiff } from '@codonlab/schema'
import type { Route } from 'next'
import Link from 'next/link'

import { Badge } from '@/components/ui/badge'

/**
 * Specification §5.5: re-runnable with one parameter changed, and diffable
 * against the previous run.
 *
 * Exact rather than inferred. The child records its parent, both runs' scores
 * are stored, and a stage whose input hash is unchanged did not re-execute —
 * which is what makes "only what that parameter affects" a fact rather than a
 * claim.
 */
function render(value: unknown): string {
  if (value === null || value === undefined) return 'not set'
  if (Array.isArray(value)) return value.join(', ')
  return String(value)
}

export function DiffPanel({ diff }: { diff: RunDiff }) {
  const reused = diff.stages.filter((stage) => stage.reused)

  return (
    <section className="border-border rounded-panel divide-border divide-y border">
      <header className="flex flex-wrap items-baseline gap-2 p-4">
        <h2 className="text-15 font-strong">Compared with the previous run</h2>
        <Link
          href={`/runs/${diff.parent_run_id}` as Route}
          className="text-12 text-accent font-mono"
        >
          {diff.parent_run_id.slice(0, 8)}
        </Link>
      </header>

      <div className="space-y-2 p-4">
        <p className="text-11 text-text-muted font-medium uppercase tracking-wide">
          Parameters changed
        </p>
        {diff.config_changes.length === 0 ? (
          <p className="text-13 text-text-muted">No parameter differs.</p>
        ) : (
          <ul className="text-13 space-y-1">
            {diff.config_changes.map((change) => (
              <li key={change.key}>
                <span className="text-text-muted">{change.key.replace(/_/g, ' ')}: </span>
                <span className="font-mono">{render(change.before)}</span>
                <span className="text-text-muted"> → </span>
                <span className="font-mono">{render(change.after)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-2 p-4">
        <p className="text-11 text-text-muted font-medium uppercase tracking-wide">Work reused</p>
        <p className="text-13 text-text">
          {reused.length} of {diff.stages.length} stages had identical inputs and did not
          re-execute.
        </p>
        <ul className="flex flex-wrap gap-1.5">
          {diff.stages.map((stage) => (
            <li key={stage.name}>
              <Badge tone={stage.reused ? 'neutral' : 'accent'}>
                {stage.name}
                {stage.reused ? ' · reused' : ' · re-ran'}
              </Badge>
            </li>
          ))}
        </ul>
        <p className="text-12 text-text-muted tabular-nums">
          Scores: {diff.scores.unchanged ?? 0} unchanged, {diff.scores.changed ?? 0} changed,{' '}
          {diff.scores.added ?? 0} added, {diff.scores.removed ?? 0} removed.
        </p>
      </div>

      <div className="space-y-2 p-4">
        <p className="text-11 text-text-muted font-medium uppercase tracking-wide">
          Ranking changes
        </p>
        <p className="text-13 text-text tabular-nums">
          {diff.entered.length} entered, {diff.left.length} left, {diff.moved.length} moved.
        </p>
        {diff.moved.length > 0 ? (
          <ul className="text-12 space-y-0.5">
            {diff.moved.slice(0, 10).map((move) => (
              <li key={move.code} className="tabular-nums">
                <span className="font-mono">{move.code}</span>
                <span className="text-text-muted">
                  {' '}
                  {move.before} → {move.after}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  )
}
