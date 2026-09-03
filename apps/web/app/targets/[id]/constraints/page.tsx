import type { Suggestion } from '@codonlab/schema'
import { ChevronLeft } from 'lucide-react'
import type { Route } from 'next'
import Link from 'next/link'

import { ErrorState } from '@/app/projects/error-state'
import { SequenceTrack, type TrackScheme } from '@/components/sequence-track'
import { ApiError, fetchConstraints, fetchSuggestions, fetchTarget, fetchTrack } from '@/lib/api'

import { ConstraintsPanel } from './constraints-panel'

export const dynamic = 'force-dynamic'

export default async function ConstraintsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params

  let target
  let track
  let constraints
  try {
    ;[target, track, constraints] = await Promise.all([
      fetchTarget(id),
      fetchTrack(id),
      fetchConstraints(id),
    ])
  } catch (error) {
    if (error instanceof ApiError) {
      return <ErrorState message={error.message} remedy={error.remedy} />
    }
    throw error
  }

  // Suggestions reach out to UniProt, so a failure here must not take the page
  // down — the manually-added constraints are still usable without them.
  let suggestions: Suggestion[] = []
  let suggestionError: string | null = null
  try {
    suggestions = await fetchSuggestions(id)
  } catch (error) {
    suggestionError = error instanceof ApiError ? error.message : 'Suggestions unavailable.'
  }

  const canonical = track.schemes.find((scheme) => Boolean(scheme.is_canonical))
  const schemes: TrackScheme[] = canonical
    ? [
        {
          id: String(canonical.id),
          label: String(canonical.label),
          kind: String(canonical.kind),
          isCanonical: true,
          labels: (canonical.labels as (string | null)[]) ?? [],
        },
      ]
    : []

  const constrained = new Set(constraints.flatMap((constraint) => constraint.positions))

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
        <h1 className="text-18 font-strong mt-1">Constraints</h1>
        <p className="text-12 text-text-muted mt-1 max-w-3xl">
          Constraints are hard filters. A variant at a constrained position is removed from the
          design set, and stays retrievable with the reason it was removed. Nothing here is applied
          until you accept it.
        </p>
      </header>

      {!target.is_designable ? (
        <div className="border-warn/30 bg-warn/8 border-b px-6 py-2">
          <p className="text-12 text-text">
            <span className="text-warn font-medium">Numbering not confirmed.</span> Constraints are
            recorded against the canonical scheme. Confirm one first, or every position here would
            be ambiguous.
          </p>
        </div>
      ) : null}

      <section className="border-border space-y-3 border-b p-6">
        <div>
          <h2 className="text-15 font-strong">Constrained positions</h2>
          <p className="text-12 text-text-muted">
            {constrained.size} of {target.length} residues constrained
            {canonical ? `, numbered in ${String(canonical.label)}` : ''}.
          </p>
        </div>
        {schemes.length > 0 ? (
          <SequenceTrack
            length={target.length}
            schemes={schemes}
            mismatches={[...constrained].sort((a, b) => a - b)}
          />
        ) : (
          <p className="text-13 text-text-muted">
            No canonical scheme, so there is nothing to draw against yet.
          </p>
        )}
      </section>

      <section className="p-6">
        <ConstraintsPanel
          targetId={target.id}
          sequenceLength={target.length}
          constraints={constraints}
          suggestions={suggestions}
          suggestionError={suggestionError}
          disabled={!target.is_designable}
        />
      </section>
    </div>
  )
}
