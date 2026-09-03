'use client'

import type { RankedVariant, Ranking } from '@codonlab/schema'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type RowData,
  type SortingState,
} from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ArrowDown, ArrowUp } from 'lucide-react'
import { memo, useMemo, useRef, useState } from 'react'

import { DemoMark } from '@/components/run/demo-mark'
import { EmptyCell } from '@/components/ui/table'
import { cn } from '@/lib/cn'
import { useWorkbench } from '@/lib/workbench-store'

/**
 * The main screen's table: every ranked variant, virtualised.
 *
 * The 60fps bar is met by keeping the work per frame constant rather than
 * proportional to the row count:
 *
 * * only the visible window plus overscan is mounted, so the DOM holds tens of
 *   rows whatever the ranking's length;
 * * rows are memoised and take primitives, so a scroll that does not change a
 *   row's props does not re-render it;
 * * selection lives in the store and each row subscribes to its own flag, so
 *   clicking a row re-renders that row rather than the viewport;
 * * cell formatting is pure and allocation-light — no date parsing, no regex,
 *   no new objects per cell.
 *
 * Semantic table markup is kept: spacer rows above and below the window give the
 * scroll its height, rather than absolutely positioning rows out of the table.
 */

/** DESIGN.md §1.6 — `--spacing-row` / `--spacing-row-compact`. Virtualisation
 *  needs the row height as a number, and this is the only place it is one.
 *  `test/workbench.test.ts` asserts these still match the design document. */
export const ROW_HEIGHT = 30
export const ROW_HEIGHT_COMPACT = 26

/** Rows rendered beyond the viewport, to cover fast scrolls without blank bands. */
const OVERSCAN = 12

export interface VariantRow extends RankedVariant {
  id: string
}

/** Column metadata this table reads, declared so `meta` is typed, not unknown. */
declare module '@tanstack/react-table' {
  // The module's own signature must be matched exactly for the declarations to
  // merge, which is why both parameters appear even though neither is used.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    numeric?: boolean
    mono?: boolean
    subtitle?: string
    width?: string
  }
}

const helper = createColumnHelper<VariantRow>()

function formatNumber(value: number | null | undefined, digits: number): string {
  return value === null || value === undefined ? '' : value.toFixed(digits)
}

const REGION_TONE: Record<string, string> = {
  core: 'text-text',
  boundary: 'text-text-muted',
  surface: 'text-text-muted',
}

export function VariantTable({
  ranking,
  rows,
  onOpen,
}: {
  ranking: Ranking
  rows: VariantRow[]
  onOpen: (code: string) => void
}) {
  const compact = useWorkbench((state) => state.compact)
  const hiddenColumns = useWorkbench((state) => state.hiddenColumns)
  const select = useWorkbench((state) => state.select)
  const focused = useWorkbench((state) => state.focused)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'rank', desc: false }])

  const columns = useMemo(() => {
    const metricColumns = ranking.metrics.map((metric) =>
      helper.accessor(
        (row) => row.cells.find((cell) => cell.metric === metric.id)?.value ?? null,
        {
          id: metric.id,
          header: metric.label,
          meta: {
            numeric: true,
            subtitle: [metric.unit, metric.sign_convention].filter(Boolean).join(' · '),
          },
          cell: (info) => {
            const cell = info.row.original.cells.find(
              (candidate) => candidate.metric === metric.id,
            )
            if (!cell) {
              return (
                <EmptyCell
                  reason={
                    ranking.unavailable[metric.id] ??
                    'No predictor produced this metric for this variant.'
                  }
                />
              )
            }
            const interval =
              metric.reports_interval && cell.uncertainty !== null
                ? ` ± ${cell.uncertainty.toFixed(2)}`
                : ''
            return (
              <>
                {cell.value.toFixed(2)}
                {interval}
                {cell.is_mock ? <DemoMark modelName={cell.model_id} /> : null}
              </>
            )
          },
        },
      ),
    )

    return [
      helper.accessor((row) => row.rank, {
        id: 'rank',
        header: 'Rank',
        meta: { numeric: true, width: 'w-14' },
        cell: (info) => info.getValue(),
      }),
      helper.accessor((row) => row.code, {
        id: 'code',
        header: 'Mutation',
        meta: { mono: true, subtitle: ranking.scheme_label, width: 'w-44' },
        cell: (info) => (
          <span className="font-mono">
            {info.row.original.code}
            <span className="text-text-faint"> {info.row.original.hgvs}</span>
          </span>
        ),
      }),
      helper.accessor((row) => row.features.region ?? '', {
        id: 'region',
        header: 'Region',
        meta: { width: 'w-28' },
        cell: (info) => {
          const { region, buried_by_ligand, rsa_with_ligands } = info.row.original.features
          if (!region) {
            return <EmptyCell reason={ranking.features_note ?? 'Geometry was not measured.'} />
          }
          return (
            <span className={REGION_TONE[region] ?? 'text-text'}>
              {region}
              {buried_by_ligand ? (
                <span
                  className="text-warn ml-1"
                  title={`Buried when the cofactor is present — RSA drops to ${formatNumber(rsa_with_ligands, 2)}. The value shown is for the protein alone.`}
                >
                  †
                </span>
              ) : null}
            </span>
          )
        },
      }),
      helper.accessor((row) => row.features.rsa, {
        id: 'rsa',
        header: 'RSA',
        meta: { numeric: true, subtitle: 'ASA / max', width: 'w-20' },
        cell: (info) =>
          info.getValue() === null ? (
            <EmptyCell reason={ranking.features_note ?? 'Geometry was not measured.'} />
          ) : (
            formatNumber(info.getValue(), 2)
          ),
      }),
      helper.accessor((row) => row.features.distance_to_active_site, {
        id: 'distance',
        header: 'To active site',
        meta: { numeric: true, subtitle: 'A, closest atoms', width: 'w-28' },
        cell: (info) =>
          info.getValue() === null ? (
            <EmptyCell reason="No active site defined — annotate catalytic residues in Constraints." />
          ) : (
            formatNumber(info.getValue(), 1)
          ),
      }),
      ...metricColumns,
      helper.accessor((row) => row.consensus, {
        id: 'consensus',
        header: 'Consensus',
        meta: { numeric: true, subtitle: 'mean rank, 1 best', width: 'w-24' },
        cell: (info) => info.getValue().toFixed(3),
      }),
      helper.accessor((row) => row.disagreement, {
        id: 'disagreement',
        header: 'Disagreement',
        meta: { numeric: true, subtitle: 'rank spread, not confidence', width: 'w-28' },
        cell: (info) => {
          const value = info.getValue()
          return value === null ? (
            <EmptyCell reason="Only one predictor scored this variant, so there is nothing to disagree about." />
          ) : (
            value.toFixed(3)
          )
        },
      }),
      helper.accessor((row) => row.filtered_by.join(','), {
        id: 'filtered',
        header: 'Filtered',
        meta: { width: 'w-32' },
        cell: (info) =>
          info.row.original.filtered_by.length === 0 ? (
            <span className="text-text-faint">—</span>
          ) : (
            <span className="text-warn" title="Removed by a constraint on this position.">
              {info.row.original.filtered_by
                .map((kind) => kind.replace(/_/g, ' '))
                .join(', ')}
            </span>
          ),
      }),
    ]
  }, [ranking])

  const table = useReactTable({
    data: rows,
    columns,
    state: {
      sorting,
      columnVisibility: Object.fromEntries(hiddenColumns.map((id) => [id, false])),
    },
    onSortingChange: setSorting,
    getRowId: (row) => row.code,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  const scrollRef = useRef<HTMLDivElement>(null)
  const rowHeight = compact ? ROW_HEIGHT_COMPACT : ROW_HEIGHT
  const modelRows = table.getRowModel().rows

  const virtualizer = useVirtualizer({
    count: modelRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowHeight,
    overscan: OVERSCAN,
  })

  const virtualRows = virtualizer.getVirtualItems()
  const paddingTop = virtualRows.length > 0 ? (virtualRows[0]?.start ?? 0) : 0
  const paddingBottom =
    virtualRows.length > 0
      ? virtualizer.getTotalSize() - (virtualRows[virtualRows.length - 1]?.end ?? 0)
      : 0

  const visibleColumns = table.getVisibleFlatColumns().length

  return (
    <div
      ref={scrollRef}
      data-testid="variant-scroll"
      className="bg-surface h-full overflow-auto"
      tabIndex={-1}
    >
      <table className="text-13 w-full border-collapse">
        <thead className="bg-surface-sunk sticky top-0 z-10">
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id} className="border-border border-b">
              {group.headers.map((header) => {
                const meta = header.column.columnDef.meta
                const sorted = header.column.getIsSorted()
                return (
                  <th
                    key={header.id}
                    scope="col"
                    className={cn(
                      'text-11 text-text-muted h-9 px-3 font-medium uppercase tracking-wide',
                      meta?.numeric ? 'text-right' : 'text-left',
                      meta?.width,
                    )}
                  >
                    <button
                      type="button"
                      onClick={header.column.getToggleSortingHandler()}
                      className={cn(
                        'inline-flex w-full items-baseline gap-1',
                        meta?.numeric ? 'justify-end' : 'justify-start',
                      )}
                    >
                      <span className="block">
                        <span className="block">
                          {flexRender(header.column.columnDef.header, header.getContext())}
                        </span>
                        {meta?.subtitle ? (
                          <span className="text-text-muted block normal-case">
                            {meta.subtitle}
                          </span>
                        ) : null}
                      </span>
                      {sorted === 'asc' ? (
                        <ArrowUp aria-hidden="true" className="size-3 shrink-0" strokeWidth={1.5} />
                      ) : sorted === 'desc' ? (
                        <ArrowDown aria-hidden="true" className="size-3 shrink-0" strokeWidth={1.5} />
                      ) : null}
                    </button>
                  </th>
                )
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {paddingTop > 0 ? (
            <tr aria-hidden>
              <td colSpan={visibleColumns} style={{ height: paddingTop }} />
            </tr>
          ) : null}

          {virtualRows.map((virtualRow) => {
            const row = modelRows[virtualRow.index]
            if (!row) return null
            return (
              <VirtualRow
                key={row.id}
                code={row.original.code}
                height={rowHeight}
                isFocused={focused === row.original.code}
                onSelect={select}
                onOpen={onOpen}
              >
                {row.getVisibleCells().map((cell) => {
                  const meta = cell.column.columnDef.meta
                  return (
                    <td
                      key={cell.id}
                      className={cn(
                        'truncate px-3 align-middle',
                        meta?.numeric && 'text-right tabular-nums',
                      )}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  )
                })}
              </VirtualRow>
            )
          })}

          {paddingBottom > 0 ? (
            <tr aria-hidden>
              <td colSpan={visibleColumns} style={{ height: paddingBottom }} />
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  )
}

/**
 * One row. Memoised, and subscribing to its own selection state only — so
 * selecting a row does not re-render the rest of the window.
 */
const VirtualRow = memo(function VirtualRow({
  code,
  height,
  isFocused,
  onSelect,
  onOpen,
  children,
}: {
  code: string
  height: number
  isFocused: boolean
  onSelect: (code: string, options?: { additive?: boolean }) => void
  onOpen: (code: string) => void
  children: React.ReactNode
}) {
  const isSelected = useWorkbench((state) => state.selected.includes(code))

  return (
    <tr
      data-code={code}
      data-selected={isSelected || undefined}
      aria-selected={isSelected}
      style={{ height }}
      className={cn(
        'border-border hover:bg-surface-sunk border-b',
        isSelected && 'bg-accent-sunk hover:bg-accent-sunk',
        isFocused && 'outline-accent -outline-offset-2 outline-2',
      )}
      onClick={(event) => onSelect(code, { additive: event.metaKey || event.ctrlKey })}
      onDoubleClick={() => onOpen(code)}
    >
      {children}
    </tr>
  )
})
