import { ChevronLeft } from 'lucide-react'
import type { Route } from 'next'
import Link from 'next/link'

import { ErrorState } from '@/app/projects/error-state'
import { DesignSetPanel } from '@/components/design/design-set-panel'
import { ApiError, fetchDesignSet } from '@/lib/api'

export const dynamic = 'force-dynamic'

export default async function DesignSetPage({
  params,
}: {
  params: Promise<{ id: string; setId: string }>
}) {
  const { id, setId } = await params

  let set
  try {
    set = await fetchDesignSet(setId)
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
          href={`/runs/${id}/workbench` as Route}
          className="text-12 text-text-muted hover:text-text inline-flex items-center gap-1"
        >
          <ChevronLeft aria-hidden="true" className="size-4" strokeWidth={1.5} />
          Variant workbench
        </Link>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <DesignSetPanel initial={set} />
      </div>
    </div>
  )
}
