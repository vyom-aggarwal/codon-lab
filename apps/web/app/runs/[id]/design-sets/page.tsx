import { ChevronLeft } from 'lucide-react'
import type { Route } from 'next'
import Link from 'next/link'

import { ErrorState } from '@/app/projects/error-state'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from '@/components/ui/table'
import { EmptyCell } from '@/components/ui/table'
import { ApiError, fetchDesignSets } from '@/lib/api'

export const dynamic = 'force-dynamic'

/** Specification §5.1 and §5.7: list-shaped things are tables, never cards. */
export default async function DesignSetsPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params

  let sets
  try {
    sets = await fetchDesignSets(id)
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
          <ChevronLeft className="size-4" strokeWidth={1.5} />
          Variant workbench
        </Link>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-4">
        <h1 className="text-18 font-strong">Design sets</h1>
        {sets.length === 0 ? (
          <p className="text-13 text-text-muted mt-2">
            No design sets yet. Select variants in the workbench and add them to a set.
          </p>
        ) : (
          <Table className="mt-4">
            <TableHead>
              <TableRow>
                <TableHeaderCell>Name</TableHeaderCell>
                <TableHeaderCell>Note</TableHeaderCell>
                <TableHeaderCell numeric>Budget</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {sets.map((set) => (
                <TableRow key={set.design_set_id}>
                  <TableCell>
                    <Link
                      href={`/runs/${id}/design-sets/${set.design_set_id}` as Route}
                      className="text-accent hover:underline"
                    >
                      {set.name}
                    </Link>
                  </TableCell>
                  <TableCell muted>{set.note ?? ''}</TableCell>
                  <TableCell numeric>
                    {set.budget_amount === null ? (
                      <EmptyCell reason="No budget has been set for this design set." />
                    ) : (
                      `${set.budget_amount.toLocaleString()} ${set.budget_currency ?? ''}`.trim()
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  )
}
