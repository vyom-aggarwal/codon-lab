import type { RankedVariant } from '@codonlab/schema'

import type { Filters, RegionFilter } from './workbench-store'

/**
 * The left rail's filters, as a pure function.
 *
 * Pure and outside the component so it can be tested without rendering ten
 * thousand rows, and so the table's render path stays free of predicate logic.
 *
 * A filter narrows what is shown. None of them changes what was computed, and
 * none of them silently drops a row for a reason the rail does not state — a
 * variant with no measured geometry is `unmeasured`, which is a visible choice
 * in the rail rather than an absence that quietly disappears.
 */
export function regionOf(row: RankedVariant): RegionFilter {
  return (row.features.region ?? 'unmeasured') as RegionFilter
}

export function applyFilters<T extends RankedVariant>(rows: T[], filters: Filters): T[] {
  const needle = filters.query.trim().toUpperCase()
  const maxDistance =
    filters.maxDistance === null || Number.isNaN(filters.maxDistance)
      ? null
      : filters.maxDistance

  return rows.filter((row) => {
    if (needle && !row.code.toUpperCase().includes(needle)) return false
    if (!filters.regions.includes(regionOf(row))) return false
    if (filters.onlyBuriedByLigand && !row.features.buried_by_ligand) return false
    if (maxDistance !== null) {
      const distance = row.features.distance_to_active_site
      // A variant with no measured distance is excluded rather than assumed
      // near or far. The rail says the column is unavailable when it is.
      if (distance === null || distance > maxDistance) return false
    }
    return true
  })
}

export function regionCounts(rows: RankedVariant[]): Record<RegionFilter, number> {
  const tally: Record<RegionFilter, number> = {
    core: 0,
    boundary: 0,
    surface: 0,
    unmeasured: 0,
  }
  for (const row of rows) tally[regionOf(row)] += 1
  return tally
}
