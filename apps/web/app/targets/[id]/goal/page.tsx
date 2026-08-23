import { ChevronLeft } from 'lucide-react'
import type { Route } from 'next'
import Link from 'next/link'

import { ErrorState } from '@/app/projects/error-state'
import { Badge } from '@/components/ui/badge'
import { ApiError, fetchGoals, fetchMeta, fetchTarget } from '@/lib/api'

import { GoalComposer } from './goal-composer'

export const dynamic = 'force-dynamic'

export default async function GoalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params

  let target
  let goals
  let meta
  try {
    ;[target, goals, meta] = await Promise.all([fetchTarget(id), fetchGoals(id), fetchMeta()])
  } catch (error) {
    if (error instanceof ApiError) {
      return <ErrorState message={error.message} remedy={error.remedy} />
    }
    throw error
  }

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-border shrink-0 border-b px-6 py-3">
        <Link
          href={`/targets/${target.id}` as Route}
          className="text-12 text-text-muted hover:text-text inline-flex items-center gap-1"
        >
          <ChevronLeft className="size-4" strokeWidth={1.5} />
          {target.name}
        </Link>
        <h1 className="text-18 font-strong mt-1">Goal</h1>
        <p className="text-12 text-text-muted mt-1 max-w-3xl">
          Describe what you want to change, in your own words. It is parsed into an explicit
          objective and shown back for you to check. Nothing runs until you confirm that parse — a
          tool that guesses what &ldquo;more thermostable&rdquo; meant is a tool you stop trusting
          after the first surprising result.
        </p>
      </header>

      {!target.is_designable ? (
        <div className="border-warn/30 bg-warn/8 border-b px-6 py-2">
          <p className="text-12 text-text">
            <span className="text-warn font-medium">Numbering not confirmed.</span> Set a canonical
            scheme on this target before writing a goal — otherwise every residue the objective
            refers to would be ambiguous.
          </p>
        </div>
      ) : null}

      <section className="p-6">
        <GoalComposer
          targetId={target.id}
          goal={goals[0] ?? null}
          disabled={!target.is_designable}
          objectiveSupport={meta.objective_support}
        />
      </section>

      {goals.length > 1 ? (
        <section className="border-border border-t p-6">
          <h2 className="text-15 font-strong mb-2">Earlier goals</h2>
          <ul className="space-y-2">
            {goals.slice(1).map((earlier) => (
              <li
                key={earlier.id}
                className="border-border rounded-panel flex items-start gap-3 border p-3"
              >
                <Badge tone={earlier.is_confirmed ? 'positive' : 'neutral'}>
                  {earlier.is_confirmed ? 'Confirmed' : 'Unconfirmed'}
                </Badge>
                <div className="min-w-0 space-y-1">
                  <p className="text-13 text-text">{earlier.restatement}</p>
                  <p className="text-12 text-text-faint italic">&ldquo;{earlier.raw_text}&rdquo;</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}
