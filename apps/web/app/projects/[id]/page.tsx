import type { Route } from 'next'
import { ChevronLeft } from 'lucide-react'
import Link from 'next/link'

import { ErrorState } from '@/app/projects/error-state'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from '@/components/ui/table'
import { ApiError, fetchProject } from '@/lib/api'

import { AddTarget } from './add-target'

export const dynamic = 'force-dynamic'

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params

  let project
  try {
    project = await fetchProject(id)
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
          href="/projects"
          className="text-12 text-text-muted hover:text-text inline-flex items-center gap-1"
        >
          <ChevronLeft aria-hidden="true" className="size-4" strokeWidth={1.5} />
          Projects
        </Link>
        <h1 className="text-24 font-strong mt-1">{project.name}</h1>
        <div className="text-12 text-text-muted mt-1 flex flex-wrap items-center gap-3">
          {project.organism ? <span className="italic">{project.organism}</span> : null}
          {project.objective ? <span>{project.objective}</span> : null}
        </div>
      </header>

      <section className="border-border border-b p-4">
        <h2 className="text-15 font-strong mb-1">Targets</h2>
        <p className="text-12 text-text-muted mb-3 max-w-2xl">
          A target cannot be designed against until its residue numbering has been reconciled and a
          canonical scheme confirmed. Until then every mutation code on it would be ambiguous.
        </p>

        {project.targets.length === 0 ? (
          <p className="text-13 text-text-muted mb-4">No target loaded yet. Add one below.</p>
        ) : (
          <div className="border-border rounded-panel mb-4 overflow-hidden border">
            <Table>
              <TableHead>
                <TableRow className="hover:bg-surface-sunk">
                  <TableHeaderCell>Target</TableHeaderCell>
                  <TableHeaderCell>Accession</TableHeaderCell>
                  <TableHeaderCell>Organism</TableHeaderCell>
                  <TableHeaderCell numeric>Length</TableHeaderCell>
                  <TableHeaderCell>Numbering</TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {project.targets.map((target) => (
                  <TableRow key={target.id}>
                    <TableCell className="font-medium">
                      <Link
                        href={`/targets/${target.id}` as Route}
                        className="hover:text-accent underline-offset-2 hover:underline"
                      >
                        {target.name}
                      </Link>
                    </TableCell>
                    <TableCell mono muted>
                      {target.uniprot_accession ?? '—'}
                    </TableCell>
                    <TableCell muted className="italic">
                      {target.organism ?? '—'}
                    </TableCell>
                    <TableCell numeric muted>
                      {target.length} aa
                    </TableCell>
                    <TableCell>
                      {target.is_designable ? (
                        <Badge tone="positive">{target.canonical_scheme_label}</Badge>
                      ) : (
                        <Badge tone="warn">Not reconciled</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        <AddTarget projectId={project.id} />
      </section>
    </div>
  )
}
