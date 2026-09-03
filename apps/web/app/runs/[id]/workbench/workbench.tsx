'use client'

import type { Ranking, Run, ScoreCell } from '@codonlab/schema'
import { useQuery } from '@tanstack/react-query'
import { Columns3 } from 'lucide-react'
import type { Route } from 'next'
import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { AddToSetDialog } from '@/components/design/add-to-set-dialog'
import { InlineError } from '@/components/inline-error'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { FilterRail } from '@/components/workbench/filter-rail'
import { Inspector } from '@/components/workbench/inspector'
import { ProvenanceDrawer } from '@/components/workbench/provenance-drawer'
import { Resizer } from '@/components/workbench/resizer'
import { VariantTable, type VariantRow } from '@/components/workbench/variant-table'
import * as api from '@/lib/api'
import { applyFilters, regionCounts } from '@/lib/workbench-filter'
import {
  INSPECTOR_MAX,
  INSPECTOR_MIN,
  RAIL_MAX,
  RAIL_MIN,
  useWorkbench,
} from '@/lib/workbench-store'

/**
 * Screen §5.6, the main one: three panes, the whole ranking in the middle.
 *
 * The full ranking is fetched once and filtered in memory. That is deliberate:
 * scrolling and filtering ten thousand rows must not wait on a round trip, and
 * the ranking is a pure function of a finished run, so it cannot change under
 * the user while they work.
 */

/** The ranking endpoint applies the run's budget unless a limit is given. */
const ALL_ROWS = 100000

const COLUMN_LABELS: { id: string; label: string; disabled?: string }[] = [
  { id: 'rank', label: 'Rank' },
  { id: 'code', label: 'Mutation' },
  { id: 'region', label: 'Region' },
  { id: 'rsa', label: 'RSA' },
  { id: 'distance', label: 'To active site' },
  { id: 'consensus', label: 'Consensus' },
  { id: 'disagreement', label: 'Disagreement' },
  { id: 'filtered', label: 'Filtered' },
  // Present so the absence is legible, disabled so it cannot be switched on to
  // reveal a column of dashes. A column where every cell is an em dash trains
  // the reader to stop reading em dashes, and the dash means something specific.
  { id: 'conservation', label: 'Conservation', disabled: 'Requires MSA (Phase 6)' },
]

export function Workbench({
  run,
  initialRanking,
  targetName,
  apiBase,
}: {
  run: Run
  initialRanking: Ranking
  targetName: string
  apiBase: string
}) {
  const filters = useWorkbench((state) => state.filters)
  const selected = useWorkbench((state) => state.selected)
  const focused = useWorkbench((state) => state.focused)
  const select = useWorkbench((state) => state.select)
  const toggle = useWorkbench((state) => state.toggle)
  const focus = useWorkbench((state) => state.focus)
  const clearSelection = useWorkbench((state) => state.clearSelection)
  const railWidth = useWorkbench((state) => state.railWidth)
  const inspectorWidth = useWorkbench((state) => state.inspectorWidth)
  const setRailWidth = useWorkbench((state) => state.setRailWidth)
  const setInspectorWidth = useWorkbench((state) => state.setInspectorWidth)
  const hiddenColumns = useWorkbench((state) => state.hiddenColumns)
  const toggleColumn = useWorkbench((state) => state.toggleColumn)

  const [tracedCell, setTracedCell] = useState<ScoreCell | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  const designSets = useQuery({
    queryKey: ['design-sets', run.id],
    queryFn: () => api.fetchDesignSets(run.id),
    enabled: selected.length > 0,
    staleTime: 30_000,
  })

  const query = useQuery({
    queryKey: ['ranking', run.id, filters.includeRemoved],
    queryFn: () =>
      api.fetchRanking(run.id, ALL_ROWS, { includeFiltered: filters.includeRemoved }),
    initialData: filters.includeRemoved ? undefined : initialRanking,
    staleTime: Infinity,
  })
  const ranking = query.data ?? initialRanking

  const allRows = useMemo<VariantRow[]>(
    () => ranking.rows.map((row) => ({ ...row, id: row.code })),
    [ranking],
  )

  const counts = useMemo(() => regionCounts(allRows), [allRows])
  const rows = useMemo(() => applyFilters(allRows, filters), [allRows, filters])

  const focusedRow = useMemo(
    () => rows.find((row) => row.code === focused) ?? null,
    [rows, focused],
  )

  const openInspector = useCallback(
    (code: string) => {
      focus(code)
    },
    [focus],
  )

  // DESIGN.md §3: every table has a keyboard path. j/k move, x selects,
  // Enter opens the inspector, Esc closes the topmost layer.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null
      if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return

      const index = rows.findIndex((row) => row.code === focused)
      if (event.key === 'j' || event.key === 'ArrowDown') {
        event.preventDefault()
        const next = rows[Math.min(rows.length - 1, index + 1)] ?? rows[0]
        if (next) focus(next.code)
      } else if (event.key === 'k' || event.key === 'ArrowUp') {
        event.preventDefault()
        const previous = rows[Math.max(0, index - 1)] ?? rows[0]
        if (previous) focus(previous.code)
      } else if (event.key === 'x') {
        if (focused) {
          event.preventDefault()
          toggle(focused)
        }
      } else if (event.key === 'Enter') {
        if (focused) {
          event.preventDefault()
          select(focused)
        }
      } else if (event.key === 'Escape') {
        if (drawerOpen) setDrawerOpen(false)
        else clearSelection()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [rows, focused, focus, toggle, select, clearSelection, drawerOpen])

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="border-border flex shrink-0 flex-wrap items-center gap-3 border-b px-4 py-2">
        <h1 className="text-15 font-strong">Variant workbench</h1>
        <span className="text-12 text-text-muted">{targetName}</span>
        {ranking.is_demo ? <Badge tone="warn">Synthetic output</Badge> : null}
        <span className="text-12 text-text-muted tabular-nums">
          {ranking.total_ranked.toLocaleString()} ranked
          {ranking.total_filtered > 0
            ? `, ${ranking.total_filtered.toLocaleString()} removed by constraints`
            : ''}
        </span>

        <div className="ml-auto flex items-center gap-2">
          <Popover>
            <PopoverTrigger asChild>
              <Button size="sm">
                <Columns3 aria-hidden="true" strokeWidth={1.5} />
                Columns
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-56 p-2">
              <ul className="space-y-1">
                {COLUMN_LABELS.map((column) => (
                  <li key={column.id}>
                    <label
                      className="flex items-center gap-2"
                      title={column.disabled ?? undefined}
                    >
                      <input
                        type="checkbox"
                        className="accent-accent"
                        disabled={Boolean(column.disabled)}
                        checked={!column.disabled && !hiddenColumns.includes(column.id)}
                        onChange={() => toggleColumn(column.id)}
                      />
                      <span
                        className={column.disabled ? 'text-13 text-text-faint' : 'text-13 text-text'}
                      >
                        {column.label}
                      </span>
                      {column.disabled ? (
                        <span className="text-11 text-text-faint ml-auto">
                          {column.disabled}
                        </span>
                      ) : null}
                    </label>
                  </li>
                ))}
              </ul>
            </PopoverContent>
          </Popover>
        </div>
      </header>

      {query.isError ? (
        <InlineError
          message="The ranking could not be loaded."
          remedy="Reload the page. If it persists, check `docker compose logs api`."
        />
      ) : null}

      <div className="flex min-h-0 flex-1">
        <aside
          className="bg-surface border-border shrink-0 overflow-hidden border-r"
          style={{ width: railWidth }}
          aria-label="Filters"
        >
          <FilterRail
            ranking={ranking}
            counts={counts}
            shown={rows.length}
            total={allRows.length}
          />
        </aside>
        <Resizer
          label="Resize the filter rail"
          value={railWidth}
          onChange={setRailWidth}
          min={RAIL_MIN}
          max={RAIL_MAX}
        />

        <main className="min-w-0 flex-1">
          <VariantTable ranking={ranking} rows={rows} onOpen={openInspector} />
        </main>

        <Resizer
          label="Resize the inspector"
          value={inspectorWidth}
          onChange={setInspectorWidth}
          min={INSPECTOR_MIN}
          max={INSPECTOR_MAX}
          direction="left"
        />
        <aside
          className="bg-surface border-border shrink-0 overflow-hidden border-l"
          style={{ width: inspectorWidth }}
          aria-label="Inspector"
        >
          <Inspector
            variant={focusedRow}
            ranking={ranking}
            run={run}
            targetId={run.target_id}
            apiBase={apiBase}
            tracedCell={tracedCell}
            onTrace={(cell) => {
              setTracedCell(cell)
              setDrawerOpen(true)
            }}
          />
        </aside>

        {drawerOpen && focusedRow ? (
          <div className="w-inspector shrink-0" aria-label="Provenance">
            <ProvenanceDrawer
              cell={tracedCell}
              variant={focusedRow}
              run={run}
              featuresManifest={ranking.features_manifest as Record<string, unknown>}
              onClose={() => setDrawerOpen(false)}
            />
          </div>
        ) : null}
      </div>

      <footer className="border-border bg-surface-sunk flex shrink-0 items-center gap-4 border-t px-4 py-1.5">
        <span className="text-12 text-text tabular-nums">
          {selected.length.toLocaleString()} selected
        </span>
        <span className="text-12 text-text-muted tabular-nums">
          {rows.length.toLocaleString()} of {allRows.length.toLocaleString()} shown
        </span>
        {selected.length > 0 ? (
          <>
            <AddToSetDialog
              runId={run.id}
              codes={selected}
              existing={designSets.data ?? []}
              onAdded={clearSelection}
            />
            <Button size="sm" variant="ghost" onClick={clearSelection}>
              Clear selection
            </Button>
          </>
        ) : null}
        <Link
          href={`/runs/${run.id}/design-sets` as Route}
          className="text-12 text-text-muted hover:text-text"
        >
          Design sets
        </Link>
        <span className="text-12 text-text-faint ml-auto">
          j / k move · x selects · Enter opens · Esc closes
        </span>
      </footer>
    </div>
  )
}
