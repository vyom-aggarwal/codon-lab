import { ChevronLeft } from 'lucide-react'
import type { Route } from 'next'
import Link from 'next/link'

import { ErrorState } from '@/app/projects/error-state'
import { ApiError, fetchRanking, fetchRun, fetchTarget } from '@/lib/api'

import { Workbench } from './workbench'

export const dynamic = 'force-dynamic'

/** The ranking endpoint applies the run's budget unless a limit is given. */
const ALL_ROWS = 100000

export default async function WorkbenchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params

  let run
  let ranking
  try {
    run = await fetchRun(id)
    ranking = await fetchRanking(id, ALL_ROWS)
  } catch (error) {
    if (error instanceof ApiError) {
      return <ErrorState message={error.message} remedy={error.remedy} />
    }
    throw error
  }

  if (run.status !== 'succeeded') {
    return (
      <div className="p-6">
        <ErrorState
          message={`This run is ${run.status}, so it has no ranking to work through.`}
          remedy="Open the run to see which stage it stopped at."
        />
      </div>
    )
  }

  const target = await fetchTarget(run.target_id)

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-border shrink-0 border-b px-4 py-1.5">
        <Link
          href={`/runs/${run.id}` as Route}
          className="text-12 text-text-muted hover:text-text inline-flex items-center gap-1"
        >
          <ChevronLeft aria-hidden="true" className="size-4" strokeWidth={1.5} />
          Run {run.id.slice(0, 8)}
        </Link>
      </div>
      <div className="min-h-0 flex-1">
        <Workbench
          run={run}
          initialRanking={ranking}
          targetName={target.name}
          // The browser talks to the API directly for the structure file; the
          // server-side internal URL would not resolve from a user's machine.
          apiBase={process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}
        />
      </div>
    </div>
  )
}
