import { ChevronLeft } from 'lucide-react'
import type { Route } from 'next'
import Link from 'next/link'

import { ErrorState } from '@/app/projects/error-state'
import { ApiError, fetchGoal, fetchMeta, fetchRun, fetchTarget } from '@/lib/api'

import { RunView } from './run-view'

export const dynamic = 'force-dynamic'

/**
 * Screen §5.5. The server renders what is true at request time; the client keeps
 * it current while the run is moving. Both read the same endpoint, so a reloaded
 * page and a polled one cannot disagree.
 */
export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params

  let run
  let meta
  try {
    ;[run, meta] = await Promise.all([fetchRun(id), fetchMeta()])
  } catch (error) {
    if (error instanceof ApiError) {
      return <ErrorState message={error.message} remedy={error.remedy} />
    }
    throw error
  }

  const [target, goal] = await Promise.all([fetchTarget(run.target_id), fetchGoal(run.goal_id)])

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-border shrink-0 border-b px-6 py-3">
        <Link
          href={`/targets/${target.id}` as Route}
          className="text-12 text-text-muted hover:text-text inline-flex items-center gap-1"
        >
          <ChevronLeft aria-hidden="true" className="size-4" strokeWidth={1.5} />
          {target.name}
        </Link>
      </header>

      <section className="p-6">
        <RunView
          initialRun={run}
          initialMeta={meta}
          targetName={target.name}
          restatement={goal.restatement}
        />
      </section>
    </div>
  )
}
