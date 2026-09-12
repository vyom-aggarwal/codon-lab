'use client'

import type { Meta, Run, RunStatus } from '@codonlab/schema'
import { useQuery } from '@tanstack/react-query'
import type { Route } from 'next'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState, useTransition } from 'react'

import { cancelRunAction, rerunAction } from '@/app/actions'
import { InlineError } from '@/components/inline-error'
import { DiffPanel } from '@/components/run/diff-panel'
import { FilteredPanel } from '@/components/run/filtered-panel'
import { RankedTable } from '@/components/run/ranked-table'
import { StageList } from '@/components/run/stage-list'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/components/ui/toast'
import * as api from '@/lib/api'
import { noWorkerRemedy, serverErrorRemedy } from '@/lib/remedies'

/** How many ranked rows the run view previews. The workbench is Phase 5. */
const PREVIEW_ROWS = 10

const STATUS_TONE: Record<RunStatus, BadgeTone> = {
  pending: 'neutral',
  running: 'accent',
  succeeded: 'positive',
  failed: 'negative',
  cancelled: 'neutral',
}

type Failure = { message: string; remedy: string } | null

export function RunView({
  initialRun,
  initialMeta,
  targetName,
  restatement,
}: {
  initialRun: Run
  initialMeta: Meta
  targetName: string
  restatement: string
}) {
  const router = useRouter()
  const toast = useToast()
  const [pending, startTransition] = useTransition()
  const [error, setError] = useState<Failure>(null)
  const [budget, setBudget] = useState<string>(String(initialRun.config.max_variants ?? ''))

  const runQuery = useQuery({
    queryKey: ['run', initialRun.id],
    queryFn: () => api.fetchRun(initialRun.id),
    initialData: initialRun,
    // Polling stops the moment the API says the run is terminal. The client
    // does not keep its own list of which statuses are final.
    refetchInterval: (query) => (query.state.data?.is_terminal ? false : 1000),
  })
  const run = runQuery.data

  // Only while a run is waiting: this is the one moment queue health explains
  // something the run itself cannot.
  const metaQuery = useQuery({
    queryKey: ['meta'],
    queryFn: () => api.fetchMeta(),
    initialData: initialMeta,
    refetchInterval: run.status === 'pending' ? 3000 : false,
  })

  const finished = run.status === 'succeeded'

  const rankingQuery = useQuery({
    queryKey: ['ranking', run.id, PREVIEW_ROWS],
    queryFn: () => api.fetchRanking(run.id, PREVIEW_ROWS),
    enabled: finished,
  })

  const filteredQuery = useQuery({
    queryKey: ['filtered', run.id],
    queryFn: () => api.fetchFiltered(run.id),
    enabled: finished,
  })

  const diffQuery = useQuery({
    queryKey: ['diff', run.id],
    queryFn: () => api.fetchDiff(run.id),
    enabled: run.is_terminal && run.parent_run_id !== null,
  })

  function cancel() {
    setError(null)
    startTransition(async () => {
      const result = await cancelRunAction(run.id)
      if (!result.ok) {
        setError({ message: result.message, remedy: result.remedy })
        return
      }
      toast({ title: 'Run cancelled', description: 'Stages already finished are kept on record.' })
      void runQuery.refetch()
    })
  }

  function rerunWithBudget() {
    setError(null)
    const parsed = budget.trim() === '' ? undefined : Number(budget)
    startTransition(async () => {
      const result = await rerunAction(
        run.id,
        parsed === undefined ? {} : { max_variants: parsed },
      )
      if (!result.ok) {
        setError({ message: result.message, remedy: result.remedy })
        return
      }
      toast({ title: 'Design run started', description: 'Comparable against this run.' })
      router.push(`/runs/${result.data.id}` as Route)
    })
  }

  const queue = metaQuery.data.queue
  const stalled = run.status === 'pending' && (!queue.connected || queue.workers === 0)

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-18 font-strong">Design run</h1>
          <Badge tone={STATUS_TONE[run.status]}>{run.status}</Badge>
          {run.is_demo ? <Badge tone="warn">Synthetic output</Badge> : null}
          {run.parent_run_id ? <Badge tone="neutral">Re-run</Badge> : null}
        </div>
        <p className="text-13 text-text-muted">
          {targetName} — {restatement}
        </p>
        {/* The run's own parameters, not the objective's. They can differ: a
            re-run changes one of these while the objective stays put. */}
        <p className="text-12 text-text-muted">
          {(run.config.predictors ?? []).join(', ')}
          {run.config.max_variants
            ? ` · selects the top ${run.config.max_variants.toLocaleString()}`
            : ' · no budget, nothing truncated'}
          {run.config.override_constraints ? ' · constraints overridden' : ''}
        </p>
        <p className="text-11 text-text-faint font-mono" title={run.input_hash}>
          run {run.id.slice(0, 8)} · inputs {run.input_hash.replace(/^sha256:/, '').slice(0, 16)}
        </p>
      </header>

      {error ? <InlineError message={error.message} remedy={error.remedy} /> : null}

      {stalled ? (
        <div className="border-warn/30 bg-warn/8 rounded-panel border p-3">
          <p className="text-13 text-text">
            <span className="text-warn font-medium">This run is queued and nothing is consuming the queue.</span>{' '}
            {queue.connected
              ? 'Redis is reachable but no worker is running.'
              : `The job queue is unreachable${queue.detail ? `: ${queue.detail}` : '.'}`}
          </p>
          <p className="text-12 text-text-muted mt-1">
            {noWorkerRemedy()} The run will pick up where it is.
          </p>
        </div>
      ) : null}

      {run.error ? (
        <InlineError
          message={run.error}
          remedy="The stage that failed is marked below, with its log. Fix the cause and start a new run."
        />
      ) : null}

      <section className="space-y-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-15 font-strong">Pipeline</h2>
          {!run.is_terminal ? (
            <Button size="sm" onClick={cancel} disabled={pending}>
              Cancel run
            </Button>
          ) : null}
        </div>
        <StageList stages={run.stages} />
      </section>

      {finished ? (
        <section className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-15 font-strong">Ranked variants</h2>
            {rankingQuery.data ? (
              <p className="text-12 text-text-muted tabular-nums">
                {rankingQuery.data.total_ranked.toLocaleString()} ranked,{' '}
                {rankingQuery.data.total_filtered.toLocaleString()} removed by constraints
                {rankingQuery.data.budget === null
                  ? ', no budget stated'
                  : `, budget ${rankingQuery.data.budget.toLocaleString()}`}
                . Showing the top {PREVIEW_ROWS}.
              </p>
            ) : null}
          </div>

          {rankingQuery.isPending ? (
            <RankingSkeleton />
          ) : rankingQuery.data ? (
            <RankedTable ranking={rankingQuery.data} />
          ) : (
            <InlineError
              message="The ranking could not be loaded."
              remedy={serverErrorRemedy()}
            />
          )}

          {filteredQuery.data ? <FilteredPanel filtered={filteredQuery.data} /> : null}

          <Button variant="primary" asChild>
            <Link href={`/runs/${run.id}/workbench` as Route}>Open the variant workbench</Link>
          </Button>
        </section>
      ) : null}

      {run.is_terminal ? (
        <section className="border-border rounded-panel space-y-2 border p-4">
          <h2 className="text-15 font-strong">Re-run with one parameter changed</h2>
          <p className="text-12 text-text-muted">
            Stages whose inputs are unchanged are reused rather than recomputed, so the comparison
            is exact.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <label className="space-y-1">
              <span className="text-11 text-text-muted block font-medium uppercase tracking-wide">
                Variants to select
              </span>
              <Input
                aria-label="Variants to select"
                className="w-32"
                value={budget}
                inputMode="numeric"
                placeholder="No budget"
                onChange={(event) => setBudget(event.target.value)}
              />
            </label>
            <Button onClick={rerunWithBudget} disabled={pending}>
              Re-run
            </Button>
          </div>
        </section>
      ) : null}

      {diffQuery.data ? <DiffPanel diff={diffQuery.data} /> : null}
    </div>
  )
}

/**
 * Skeletons match the geometry of the table they stand in for, per DESIGN.md §5.
 * Never a centred spinner over the page.
 */
function RankingSkeleton() {
  return (
    <div className="border-border rounded-panel divide-border divide-y border" aria-hidden>
      {Array.from({ length: 6 }, (_, index) => (
        <div key={index} className="h-row flex items-center gap-4 px-3">
          <div className="bg-surface-sunk h-2 w-8 rounded-control" />
          <div className="bg-surface-sunk h-2 w-24 rounded-control" />
          <div className="bg-surface-sunk ml-auto h-2 w-16 rounded-control" />
          <div className="bg-surface-sunk h-2 w-16 rounded-control" />
        </div>
      ))}
    </div>
  )
}
