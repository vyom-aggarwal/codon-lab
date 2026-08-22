import type { RankedVariant, Ranking, Run } from '@catalyst/schema'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'

import { Workbench } from '@/app/runs/[id]/workbench/workbench'
import { ROW_HEIGHT } from '@/components/workbench/variant-table'

/**
 * The Phase 5 gate, as the owner rewrote it: **constant work per scroll update**.
 *
 * Frame rate is not asserted here and must not be. It cannot be measured in
 * jsdom, and it could not be measured from an agent session either — the browser
 * pane runs hidden, so nothing composites and `requestAnimationFrame` never
 * fires. What *is* assertable is the property 60fps rests on, and it is the one
 * that generalises: the amount of DOM the table builds does not grow with the
 * number of ranked variants.
 *
 * Two things are checked, both structural:
 *
 * 1. rendering 10,000 rows mounts the same number of `<tr>` as rendering 100;
 * 2. the scroll height still accounts for every row, so virtualisation is
 *    windowing the view rather than quietly dropping data.
 *
 * The second matters as much as the first. A table that rendered 32 rows and
 * forgot the other 10,418 would pass a node-count check and be catastrophically
 * wrong.
 */

vi.mock('@/components/workbench/structure-viewer', () => ({
  StructureViewer: () => null,
}))

/** jsdom reports zero-height elements, so a virtualiser correctly renders
 *  nothing. TanStack Virtual measures offsetHeight, not clientHeight. */
beforeAll(() => {
  for (const [property, value] of [
    ['offsetHeight', 600],
    ['offsetWidth', 1200],
    ['clientHeight', 600],
    ['clientWidth', 1200],
  ] as const) {
    Object.defineProperty(HTMLElement.prototype, property, {
      configurable: true,
      get: () => value,
    })
  }
  HTMLElement.prototype.getBoundingClientRect = function getBoundingClientRect() {
    return {
      width: 1200, height: 600, top: 0, left: 0, right: 1200, bottom: 600, x: 0, y: 0,
      toJSON: () => ({}),
    } as DOMRect
  }
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
})

const MODEL_VERSION_ID = '967f9a8d-18ec-45d4-89a8-d873038e0635'

const run: Run = {
  id: 'd6fcc1b0-028f-4e53-9c8e-171f6ff0ab49',
  project_id: '11111111-1111-1111-1111-111111111111',
  target_id: '22222222-2222-2222-2222-222222222222',
  goal_id: '33333333-3333-3333-3333-333333333333',
  status: 'succeeded',
  config: { predictors: ['mock_stability'], max_variants: null, override_constraints: false },
  input_hash: 'sha256:abc123',
  parent_run_id: null,
  created_at: '2026-08-16T00:00:00+00:00',
  started_at: '2026-08-16T00:00:01+00:00',
  finished_at: '2026-08-16T00:00:09+00:00',
  error: null,
  is_demo: true,
  is_terminal: true,
  stages: [],
}

const RESIDUES = 'ACDEFGHIKLMNPQRSTVWY'

/** Distinct, plausible rows — not the same row repeated, which a naive
 *  implementation could deduplicate and appear to virtualise. */
function rows(count: number): RankedVariant[] {
  return Array.from({ length: count }, (_, index) => {
    const position = Math.floor(index / 19) + 1
    const wild = RESIDUES[position % 20] ?? 'A'
    const mutant = RESIDUES[index % 20] ?? 'V'
    return {
      rank: index + 1,
      code: `${wild}${position}${mutant}_${index}`,
      hgvs: `p.Xaa${position}Xaa`,
      label: String(position),
      sequence_position: position,
      features: {
        author_label: String(position),
        asa: 30,
        rsa: 0.2,
        region: 'core' as const,
        buried_by_ligand: false,
        rsa_with_ligands: 0.2,
        distance_to_active_site: null,
      },
      filtered_by: [],
      consensus: 1 - index / (count + 1),
      disagreement: 0.01,
      sources_scored: 1,
      cells: [
        {
          metric: 'ddg_kcal_per_mol',
          value: -0.5,
          uncertainty: 0.3,
          ci_low: -1.1,
          ci_high: 0.1,
          model_version_id: MODEL_VERSION_ID,
          model_id: 'mock_stability',
          is_mock: true,
        },
      ],
    }
  })
}

function ranking(count: number): Ranking {
  return {
    run_id: run.id,
    scheme_label: 'P08659 chain A, author numbering',
    metrics: [
      {
        id: 'ddg_kcal_per_mol',
        label: 'Predicted ΔΔG',
        unit: 'kcal/mol',
        sign_convention: 'destabilizing positive',
        higher_is_better: false,
        reports_interval: true,
      },
    ],
    unavailable: {},
    total_scored: count,
    total_filtered: 0,
    total_ranked: count,
    budget: null,
    is_demo: true,
    features_manifest: {},
    features_note: null,
    rows: rows(count),
  }
}

function renderWith(count: number) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <QueryClientProvider client={client}>
      <Workbench
        run={run}
        initialRanking={ranking(count)}
        targetName="Scale check"
        apiBase="http://localhost:8000"
      />
    </QueryClientProvider>,
  )
  const container = view.container
  const mounted = container.querySelectorAll('tr[data-code]').length
  const spacers = [...container.querySelectorAll('tbody tr[aria-hidden] td')].reduce(
    (total, cell) => total + Number.parseFloat((cell as HTMLElement).style.height || '0'),
    0,
  )
  return { view, container, mounted, spacers }
}

describe('the table does constant work regardless of how many variants there are', () => {
  it('mounts the same number of rows for 10,000 variants as for 100', () => {
    const small = renderWith(100)
    expect(small.mounted).toBeGreaterThan(0)
    small.view.unmount()

    const large = renderWith(10_000)
    expect(large.mounted).toBe(small.mounted)
    large.view.unmount()
  })

  it('mounts a bounded number of rows, not one per variant', () => {
    const large = renderWith(10_000)
    // A 600px viewport at 30px rows is 20 visible, plus overscan either side.
    expect(large.mounted).toBeLessThan(100)
    expect(large.mounted).toBeGreaterThanOrEqual(20)
    large.view.unmount()
  })

  it('keeps total DOM nodes flat as the ranking grows a hundredfold', () => {
    const small = renderWith(100)
    const smallNodes = small.container.querySelectorAll('*').length
    small.view.unmount()

    const large = renderWith(10_000)
    const largeNodes = large.container.querySelectorAll('*').length
    large.view.unmount()

    // Not "smaller than 10,000" — flat. Any growth proportional to row count
    // would show up here long before it became a frame-rate problem.
    expect(largeNodes).toBeLessThanOrEqual(smallNodes * 1.1)
  })

  it('still accounts for every row in the scroll height', () => {
    // The check that stops the one above from being satisfied by a table that
    // renders 32 rows and forgets the rest.
    const count = 10_000
    const { mounted, spacers, view } = renderWith(count)
    const accounted = spacers + mounted * ROW_HEIGHT
    expect(accounted).toBe(count * ROW_HEIGHT)
    view.unmount()
  })

  it('scales the scroll height with the row count', () => {
    const small = renderWith(100)
    const smallTotal = small.spacers + small.mounted * ROW_HEIGHT
    small.view.unmount()

    const large = renderWith(10_000)
    const largeTotal = large.spacers + large.mounted * ROW_HEIGHT
    large.view.unmount()

    expect(smallTotal).toBe(100 * ROW_HEIGHT)
    expect(largeTotal).toBe(10_000 * ROW_HEIGHT)
  })
})
