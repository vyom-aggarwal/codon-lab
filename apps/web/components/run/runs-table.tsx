import type { Run, RunStatus } from '@codonlab/schema'
import type { Route } from 'next'
import Link from 'next/link'

import { Badge, type BadgeTone } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from '@/components/ui/table'

const TONE: Record<RunStatus, BadgeTone> = {
  pending: 'neutral',
  running: 'accent',
  succeeded: 'positive',
  failed: 'negative',
  cancelled: 'neutral',
}

function duration(run: Run): string {
  if (!run.started_at || !run.finished_at) return '—'
  const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
  return `${(ms / 1000).toFixed(1)} s`
}

/** Runs on a target, most recent first. Tables, not cards. */
export function RunsTable({ runs }: { runs: Run[] }) {
  if (runs.length === 0) {
    return (
      <p className="text-13 text-text-muted">
        No design run yet. Confirm an objective on the goal screen, then start one.
      </p>
    )
  }

  return (
    <Table>
      <TableHead>
        <TableRow>
          <TableHeaderCell>Run</TableHeaderCell>
          <TableHeaderCell>Status</TableHeaderCell>
          <TableHeaderCell>Predictors</TableHeaderCell>
          <TableHeaderCell numeric>Budget</TableHeaderCell>
          <TableHeaderCell numeric>Runtime</TableHeaderCell>
          <TableHeaderCell>Started</TableHeaderCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {runs.map((run) => (
          <TableRow key={run.id}>
            <TableCell mono>
              <Link href={`/runs/${run.id}` as Route} className="text-accent">
                {run.id.slice(0, 8)}
              </Link>
              {run.parent_run_id ? (
                <span className="text-text-faint"> (re-run)</span>
              ) : null}
            </TableCell>
            <TableCell>
              <span className="flex items-center gap-1.5">
                <Badge tone={TONE[run.status]}>{run.status}</Badge>
                {run.is_demo ? <Badge tone="warn">Synthetic</Badge> : null}
              </span>
            </TableCell>
            <TableCell muted>{(run.config.predictors ?? []).join(', ') || '—'}</TableCell>
            <TableCell numeric muted>
              {run.config.max_variants ?? '—'}
            </TableCell>
            <TableCell numeric muted>
              {duration(run)}
            </TableCell>
            <TableCell muted>
              {run.started_at ? new Date(run.started_at).toLocaleString() : 'not started'}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
