'use client'

import type { Ranking } from '@codonlab/schema'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/cn'
import { ALL_REGIONS, useWorkbench, type RegionFilter } from '@/lib/workbench-store'

/**
 * Left rail: filters and constraint toggles, per specification §5.6.
 *
 * Every filter narrows what is shown and none of them changes what was computed
 * — the counts beside each control say how many rows it would leave, so a filter
 * that hides everything says so before it is applied rather than after.
 */

const REGION_LABEL: Record<RegionFilter, string> = {
  core: 'Core',
  boundary: 'Boundary',
  surface: 'Surface',
  unmeasured: 'Not measured',
}

export function FilterRail({
  ranking,
  counts,
  shown,
  total,
}: {
  ranking: Ranking
  counts: Record<RegionFilter, number>
  shown: number
  total: number
}) {
  const filters = useWorkbench((state) => state.filters)
  const setFilter = useWorkbench((state) => state.setFilter)
  const resetFilters = useWorkbench((state) => state.resetFilters)
  const compact = useWorkbench((state) => state.compact)
  const setCompact = useWorkbench((state) => state.setCompact)

  const geometryMeasured = Object.keys(ranking.features_manifest).length > 0
  const hasActiveSite = ranking.rows.some(
    (row) => row.features.distance_to_active_site !== null,
  )

  function toggleRegion(region: RegionFilter) {
    const next = filters.regions.includes(region)
      ? filters.regions.filter((item) => item !== region)
      : [...filters.regions, region]
    setFilter('regions', next)
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="border-border space-y-2 border-b p-4">
        <label className="block space-y-1">
          <span className="text-11 text-text-muted block font-medium uppercase tracking-wide">
            Mutation code
          </span>
          <Input
            aria-label="Filter by mutation code"
            placeholder="S77"
            value={filters.query}
            onChange={(event) => setFilter('query', event.target.value)}
            className="w-full"
          />
        </label>
        <p className="text-12 text-text-muted tabular-nums">
          {shown.toLocaleString()} of {total.toLocaleString()} shown
        </p>
      </div>

      <fieldset className="border-border space-y-1.5 border-b p-4">
        <legend className="text-11 text-text-muted font-medium uppercase tracking-wide">
          Burial
        </legend>
        {!geometryMeasured ? (
          <p className="text-12 text-text-muted">
            {ranking.features_note ?? 'Geometry was not measured for this run.'}
          </p>
        ) : null}
        {ALL_REGIONS.map((region) => (
          <label key={region} className="flex items-center gap-2">
            <input
              type="checkbox"
              className="accent-accent"
              checked={filters.regions.includes(region)}
              onChange={() => toggleRegion(region)}
            />
            <span className="text-13 text-text">{REGION_LABEL[region]}</span>
            <span className="text-12 text-text-faint ml-auto tabular-nums">
              {counts[region].toLocaleString()}
            </span>
          </label>
        ))}
        {geometryMeasured ? (
          <p className="text-12 text-text-muted pt-1">
            Core RSA &lt; {String(cutoff(ranking, 'core_rsa_below'))}, surface RSA &gt;{' '}
            {String(cutoff(ranking, 'surface_rsa_above'))}.
          </p>
        ) : null}
      </fieldset>

      <fieldset className="border-border space-y-2 border-b p-4">
        <legend className="text-11 text-text-muted font-medium uppercase tracking-wide">
          Active site
        </legend>
        {hasActiveSite ? (
          <label className="block space-y-1">
            <span className="text-12 text-text-muted">Within (A, closest atoms)</span>
            <Input
              aria-label="Maximum distance to the active site"
              inputMode="numeric"
              placeholder="any"
              value={filters.maxDistance === null ? '' : String(filters.maxDistance)}
              onChange={(event) => {
                const raw = event.target.value.trim()
                setFilter('maxDistance', raw === '' ? null : Number(raw))
              }}
              className="w-24"
            />
          </label>
        ) : (
          <p className="text-12 text-text-muted">
            No active site defined — annotate catalytic residues in Constraints.
          </p>
        )}
      </fieldset>

      <fieldset className="border-border space-y-1.5 border-b p-4">
        <legend className="text-11 text-text-muted font-medium uppercase tracking-wide">
          Constraints
        </legend>
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            className="accent-accent mt-0.5"
            checked={filters.includeRemoved}
            onChange={(event) => setFilter('includeRemoved', event.target.checked)}
          />
          <span className="text-13 text-text">
            Show removed variants
            <span className="text-12 text-text-muted block">
              Every variant a constraint filtered out, with the constraint that removed it.
            </span>
          </span>
        </label>
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            className="accent-accent mt-0.5"
            checked={filters.onlyBuriedByLigand}
            onChange={(event) => setFilter('onlyBuriedByLigand', event.target.checked)}
          />
          <span className="text-13 text-text">
            Buried by a cofactor
            <span className="text-12 text-text-muted block">
              Exposed in the protein alone, buried once cofactors are present.
            </span>
          </span>
        </label>
      </fieldset>

      <div className="space-y-2 p-4">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            className="accent-accent"
            checked={compact}
            onChange={(event) => setCompact(event.target.checked)}
          />
          <span className="text-13 text-text">Compact rows</span>
        </label>
        <Button size="sm" onClick={resetFilters} className={cn('w-full')}>
          Reset filters
        </Button>
      </div>
    </div>
  )
}

function cutoff(ranking: Ranking, key: string): unknown {
  const cutoffs = ranking.features_manifest.cutoffs
  if (cutoffs && typeof cutoffs === 'object' && key in cutoffs) {
    return (cutoffs as Record<string, unknown>)[key]
  }
  return '—'
}
