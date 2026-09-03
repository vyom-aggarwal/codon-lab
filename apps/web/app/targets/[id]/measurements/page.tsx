import { ChevronLeft } from 'lucide-react'
import type { Route } from 'next'
import Link from 'next/link'

import { ErrorState } from '@/app/projects/error-state'
import { IntakePanel } from '@/components/measurements/intake-panel'
import { ApiError, fetchTarget } from '@/lib/api'

export const dynamic = 'force-dynamic'

export default async function MeasurementsPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params

  let target
  try {
    target = await fetchTarget(id)
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
        <IntakePanel targetId={id} />
      </div>
    </div>
  )
}
