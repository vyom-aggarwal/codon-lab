import type { Route } from 'next'
import { ChevronLeft } from 'lucide-react'
import Link from 'next/link'

import { ErrorState } from '@/app/projects/error-state'
import { RunsTable } from '@/components/run/runs-table'
import { SequenceTrack, type TrackScheme } from '@/components/sequence-track'
import { Badge } from '@/components/ui/badge'
import { ApiError, fetchRuns, fetchTarget, fetchTrack } from '@/lib/api'

import { NumberingPanel } from './numbering-panel'

export const dynamic = 'force-dynamic'

export default async function TargetPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params

  let target
  let track
  let runs
  try {
    ;[target, track, runs] = await Promise.all([fetchTarget(id), fetchTrack(id), fetchRuns(id)])
  } catch (error) {
    if (error instanceof ApiError) {
      return <ErrorState message={error.message} remedy={error.remedy} />
    }
    throw error
  }

  const schemes: TrackScheme[] = track.schemes.map((scheme) => ({
    id: String(scheme.id),
    label: String(scheme.label),
    kind: String(scheme.kind),
    isCanonical: Boolean(scheme.is_canonical),
    labels: (scheme.labels as (string | null)[]) ?? [],
  }))

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-border shrink-0 border-b px-6 py-3">
        <Link
          href={`/projects/${target.project_id}` as Route}
          className="text-12 text-text-muted hover:text-text inline-flex items-center gap-1"
        >
          <ChevronLeft aria-hidden="true" className="size-4" strokeWidth={1.5} />
          Back to project
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <h1 className="text-18 font-strong">{target.name}</h1>
          {target.uniprot_accession ? (
            <Badge mono tone="neutral">
              {target.uniprot_accession}
            </Badge>
          ) : null}
          {target.is_designable ? (
            <Badge tone="positive">{target.canonical_scheme_label}</Badge>
          ) : (
            <Badge tone="warn">Numbering not confirmed</Badge>
          )}
        </div>
        <p className="text-12 text-text-muted mt-1">
          {target.organism ? <span className="italic">{target.organism}</span> : null}
          {target.organism ? ' · ' : ''}
          <span className="tabular-nums">{target.length} residues</span>
        </p>

        <nav className="mt-2 flex items-center gap-4" aria-label="Target">
          <Link
            href={`/targets/${target.id}/constraints` as Route}
            className="text-12 text-accent underline-offset-2 hover:underline"
          >
            Constraints
          </Link>
          <Link
            href={`/targets/${target.id}/goal` as Route}
            className="text-12 text-accent underline-offset-2 hover:underline"
          >
            Goal
          </Link>
          <Link
            href={`/targets/${target.id}/measurements` as Route}
            className="text-12 text-accent underline-offset-2 hover:underline"
          >
            Import measured results
          </Link>
          <Link
            href={`/targets/${target.id}/scorecard` as Route}
            className="text-12 text-accent underline-offset-2 hover:underline"
          >
            Scorecard
          </Link>
        </nav>
      </header>

      {!target.is_designable ? (
        <div className="border-warn/30 bg-warn/8 border-b px-6 py-2">
          <p className="text-12 text-text">
            <span className="text-warn font-medium">Numbering not reconciled.</span> No mutation
            code can be written against this target yet, because it would be ambiguous. Attach a
            structure, reconcile, then confirm a canonical scheme.
          </p>
        </div>
      ) : null}

      <section className="border-border space-y-3 border-b p-6">
        <div>
          <h2 className="text-15 font-strong">Numbering schemes</h2>
          <p className="text-12 text-text-muted max-w-2xl">
            Each row is one scheme over the same residues. Gaps are drawn as gaps: a region a scheme
            does not cover is left empty rather than closed up, because closing it is exactly how an
            off-by-one enters.
          </p>
        </div>
        <SequenceTrack length={target.length} schemes={schemes} />
      </section>

      <section className="p-6">
        <NumberingPanel
          targetId={target.id}
          schemes={target.numbering_schemes}
          structures={target.structures}
          hasAccession={Boolean(target.uniprot_accession)}
          isDesignable={target.is_designable}
        />
      </section>

      <section className="border-border border-t p-6">
        <h2 className="text-15 font-strong mb-2">Design runs</h2>
        <RunsTable runs={runs} />
      </section>

      <section className="border-border border-t p-6">
        <h2 className="text-15 font-strong mb-2">Sequence</h2>
        <p className="text-12 text-text-muted mb-2">
          Numbered in{' '}
          {target.canonical_scheme_label ? (
            <span className="text-text">{target.canonical_scheme_label}</span>
          ) : (
            <span className="text-warn">
              no confirmed scheme — positions shown are array index, not residue numbers
            </span>
          )}
          .
        </p>
        <SequenceBlock residues={track.residues} />
      </section>
    </div>
  )
}

function SequenceBlock({
  residues,
}: {
  residues: { index: number; residue: string; label: string | null }[]
}) {
  const rows: (typeof residues)[] = []
  for (let start = 0; start < residues.length; start += 60) {
    rows.push(residues.slice(start, start + 60))
  }

  return (
    <div className="border-border rounded-panel bg-surface-sunk overflow-x-auto border p-3">
      <div className="text-12 min-w-max space-y-1 font-mono">
        {rows.map((row) => {
          const first = row[0]
          if (!first) return null
          return (
            <div key={first.index} className="flex gap-3">
              <span className="text-text-faint w-16 shrink-0 text-right tabular-nums">
                {first.label ?? first.index}
              </span>
              <span className="text-text tracking-wider">
                {row.map((entry) => entry.residue).join('')}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
