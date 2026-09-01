import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/**
 * Workbench view state.
 *
 * ARCHITECTURE.md §7: Zustand holds selection, filters and panel sizes, and
 * never a copy of server data. Everything here is either a set of ids, a filter
 * predicate's inputs, or a pixel width — the rows themselves stay in TanStack
 * Query, so there is exactly one copy of them.
 *
 * Selection lives here rather than in the table component for a performance
 * reason as much as an architectural one: a row subscribes to its own selected
 * flag, so clicking one row re-renders one row rather than the viewport.
 */

export type RegionFilter = 'core' | 'boundary' | 'surface' | 'unmeasured'

export interface Filters {
  /** Substring match on the mutation code, e.g. `S77`. */
  query: string
  regions: RegionFilter[]
  /** Only variants within this many angstroms of the annotated active site. */
  maxDistance: number | null
  /** Only variants the cofactor buries — the ones the apo RSA misreports. */
  onlyBuriedByLigand: boolean
  /** Include the variants a constraint removed, shown with their reason. */
  includeRemoved: boolean
}

export const ALL_REGIONS: RegionFilter[] = ['core', 'boundary', 'surface', 'unmeasured']

const EMPTY_FILTERS: Filters = {
  query: '',
  regions: ALL_REGIONS,
  maxDistance: null,
  onlyBuriedByLigand: false,
  includeRemoved: false,
}

interface WorkbenchState {
  filters: Filters
  setFilter: <K extends keyof Filters>(key: K, value: Filters[K]) => void
  resetFilters: () => void

  /** Mutation codes, not row indices: a filter change must not move a selection. */
  selected: string[]
  /** The row the keyboard is on, and what the inspector shows. */
  focused: string | null
  /** Anchor for shift-range selection. */
  anchor: string | null

  select: (code: string, options?: { additive?: boolean; range?: string[] }) => void
  toggle: (code: string) => void
  clearSelection: () => void
  focus: (code: string | null) => void

  /** Persisted per user, per DESIGN.md §2. */
  railWidth: number
  inspectorWidth: number
  compact: boolean
  hiddenColumns: string[]
  setRailWidth: (width: number) => void
  setInspectorWidth: (width: number) => void
  setCompact: (compact: boolean) => void
  toggleColumn: (id: string) => void
}

export const RAIL_MIN = 180
export const RAIL_MAX = 420
export const INSPECTOR_MIN = 300
export const INSPECTOR_MAX = 640

function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value))
}

export const useWorkbench = create<WorkbenchState>()(
  persist(
    (set, get) => ({
      filters: EMPTY_FILTERS,
      setFilter: (key, value) => set({ filters: { ...get().filters, [key]: value } }),
      resetFilters: () => set({ filters: EMPTY_FILTERS }),

      selected: [],
      focused: null,
      anchor: null,

      select: (code, options) => {
        if (options?.range) {
          // Shift-range: replace with the span, so a range never accumulates
          // silently over several shift-clicks.
          set({ selected: options.range, focused: code })
          return
        }
        if (options?.additive) {
          const selected = get().selected
          set({
            selected: selected.includes(code)
              ? selected.filter((item) => item !== code)
              : [...selected, code],
            focused: code,
            anchor: code,
          })
          return
        }
        set({ selected: [code], focused: code, anchor: code })
      },
      toggle: (code) => {
        const selected = get().selected
        set({
          selected: selected.includes(code)
            ? selected.filter((item) => item !== code)
            : [...selected, code],
          anchor: code,
        })
      },
      clearSelection: () => set({ selected: [], anchor: null }),
      focus: (code) => set({ focused: code }),

      railWidth: 240,
      inspectorWidth: 380,
      compact: false,
      hiddenColumns: [],
      setRailWidth: (width) => set({ railWidth: clamp(width, RAIL_MIN, RAIL_MAX) }),
      setInspectorWidth: (width) =>
        set({ inspectorWidth: clamp(width, INSPECTOR_MIN, INSPECTOR_MAX) }),
      setCompact: (compact) => set({ compact }),
      toggleColumn: (id) => {
        const hidden = get().hiddenColumns
        set({
          hiddenColumns: hidden.includes(id)
            ? hidden.filter((item) => item !== id)
            : [...hidden, id],
        })
      },
    }),
    {
      name: 'codonlab.workbench',
      // Selection is per-run and meaningless on the next one; sizes and column
      // choices are the user's setup and outlive it.
      partialize: (state) => ({
        railWidth: state.railWidth,
        inspectorWidth: state.inspectorWidth,
        compact: state.compact,
        hiddenColumns: state.hiddenColumns,
      }),
    },
  ),
)
