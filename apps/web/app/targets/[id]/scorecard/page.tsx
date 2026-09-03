import { ChevronLeft } from 'lucide-react'
import type { Route } from 'next'
import Link from 'next/link'

import { ErrorState } from '@/app/projects/error-state'
import { ScorecardView } from '@/components/scorecard/scorecard-view'
import { ApiError, fetchTarget, fetchTargetScorecard } from '@/lib/api'

export const dynamic = 'force-dynamic'

export default async function ScorecardPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params

  let target
  let report
  try {
    ;[target, report] = await Promise.all([fetchTarget(id), fetchTargetScorecard(id)])
  } catch (error) {
    if (error instanceof ApiError) {
      return <ErrorState message={error.message} remedy={error.remedy} />
    }
    throw error
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-border shrink-0 border-b px-4 py-1.5">
        <Link
          href={`/targets/${id}` as Route}
          className="text-12 text-text-muted hover:text-text inline-flex items-center gap-1"
        >
          <ChevronLeft aria-hidden="true" className="size-4" strokeWidth={1.5} />
          {target.name}
        </Link>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <ScorecardView report={report} targetId={id} scope={target.name} />
      </div>
    </div>
  )
}
