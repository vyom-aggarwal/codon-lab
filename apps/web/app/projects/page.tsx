import type { Route } from 'next'
import type { ProjectRow } from '@codonlab/schema'
import Link from 'next/link'

import { NewProjectDialog } from './new-project-dialog'

import {
  EmptyCell,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from '@/components/ui'
import { ApiError, fetchProjects } from '@/lib/api'

import { ErrorState } from './error-state'

export const dynamic = 'force-dynamic'

/** Relative where it is useful, absolute once it stops being. */
function formatActivity(iso: string | null): string {
  if (iso === null) return '—'
  const then = new Date(iso)
  const days = Math.floor((Date.now() - then.getTime()) / 86_400_000)
  if (days < 1) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 30) return `${days} days ago`
  return then.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export default async function ProjectsPage() {
  let projects: ProjectRow[]
  try {
    projects = await fetchProjects()
  } catch (error) {
    if (error instanceof ApiError) {
      return <ErrorState message={error.message} remedy={error.remedy} />
    }
    throw error
  }

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-border flex h-12 shrink-0 items-center justify-between border-b px-6">
        <h1 className="text-18 font-strong">Projects</h1>
        <div className="flex items-center gap-4">
          <span className="text-12 text-text-muted tabular-nums">
            {projects.length} {projects.length === 1 ? 'project' : 'projects'}
          </span>
          <NewProjectDialog />
        </div>
      </header>

      {projects.length === 0 ? <EmptyState /> : <ProjectsTable projects={projects} />}
    </div>
  )
}

function ProjectsTable({ projects }: { projects: ProjectRow[] }) {
  return (
    <Table>
      <TableHead>
        <TableRow className="hover:bg-surface-sunk">
          <TableHeaderCell>Project</TableHeaderCell>
          <TableHeaderCell>Target</TableHeaderCell>
          <TableHeaderCell>Organism</TableHeaderCell>
          <TableHeaderCell>Objective</TableHeaderCell>
          <TableHeaderCell numeric>Runs</TableHeaderCell>
          <TableHeaderCell numeric>Measured variants</TableHeaderCell>
          <TableHeaderCell>Last activity</TableHeaderCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {projects.map((project) => (
          <TableRow key={project.id}>
            <TableCell className="font-medium">
              <Link
                href={`/projects/${project.id}` as Route}
                className="hover:text-accent underline-offset-2 hover:underline"
              >
                {project.name}
              </Link>
            </TableCell>
            <TableCell>
              {project.target_name ?? (
                <EmptyCell reason="No target loaded yet. Add one in target setup." />
              )}
            </TableCell>
            <TableCell muted>
              {project.organism ?? <EmptyCell reason="Organism not recorded." />}
            </TableCell>
            <TableCell muted className="max-w-md truncate" title={project.objective ?? undefined}>
              {project.objective ?? <EmptyCell reason="No objective set." />}
            </TableCell>
            <TableCell numeric muted>
              {project.run_count}
            </TableCell>
            <TableCell numeric muted>
              {project.measured_variant_count}
            </TableCell>
            <TableCell muted>{formatActivity(project.last_activity_at)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/** Empty states name the next action. */
function EmptyState() {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <div className="max-w-md space-y-3 text-center">
        <p className="text-13 text-text">No projects yet.</p>
        <p className="text-12 text-text-muted">
          A project holds one target and the design runs made against it.
        </p>
        <div className="flex justify-center">
          <NewProjectDialog />
        </div>
      </div>
    </div>
  )
}
