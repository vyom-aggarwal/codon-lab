import type { Ranking, Run } from '@codonlab/schema'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ToastProvider } from '@/components/ui/toast'
import { TooltipProvider } from '@/components/ui/tooltip'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { Workbench } from '@/app/runs/[id]/workbench/workbench'
import { useWorkbench } from '@/lib/workbench-store'

/**
 * The Phase 5 exit gate, counted rather than asserted.
 *
 * `BRIEF.md` §9: "any score traces to a model version in two clicks". The way
 * that claim rots is a component reshuffle that adds a step — an accordion to
 * open, a tab to pick, a row to expand first — and nothing notices, because a
 * test that checks the drawer *exists* still passes.
 *
 * So this counts clicks. It listens for click events on the document and
 * asserts the model version is unreachable at zero and one, and reachable at
 * two. Verified independently in a real browser with trusted clicks; this is
 * what keeps it true.
 */

// Mol* is WebGL and multi-megabyte. The inspector loads it dynamically; here it
// is replaced, because the structure viewer is not on the path being counted.
vi.mock('@/components/workbench/structure-viewer', () => ({
  StructureViewer: () => null,
}))

/**
 * jsdom gives every element a height of zero, so a virtualiser asked for the
 * visible window correctly returns nothing. Without this the table renders no
 * rows at all — and a click-counting test would then pass for the worst
 * possible reason: there is nothing to click.
 */
beforeAll(() => {
  // TanStack Virtual measures the scroll element with offsetWidth/offsetHeight,
  // not clientHeight — stubbing the wrong one leaves the window empty.
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
    return { width: 1200, height: 600, top: 0, left: 0, right: 1200, bottom: 600, x: 0, y: 0,
      toJSON: () => ({}) } as DOMRect
  }
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
})

const WEIGHTS_HASH = 'sha256:191a9b9564b90144cf36564722c8ac1205e64226395f0dba12e5984ed7d87870'
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
  stages: [
    {
      id: '44444444-4444-4444-4444-444444444444',
      ordinal: 2,
      name: 'score with Mock stability predictor',
      status: 'succeeded',
      runtime_ms: 4547,
      input_hash: 'sha256:d93ab89ab420',
      logs: 'Wrote 10,450 scores.',
      error: null,
      model: {
        id: MODEL_VERSION_ID,
        model_id: 'mock_stability',
        name: 'Mock stability predictor',
        version: '0.1.0',
        weights_hash: WEIGHTS_HASH,
        modality: 'stability',
        citation: 'No citation. Synthetic output. Not a model and not a prediction.',
        is_mock: true,
      },
    },
  ],
}

const ranking: Ranking = {
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
  total_scored: 10450,
  total_filtered: 0,
  total_ranked: 10450,
  budget: null,
  is_demo: true,
  features_manifest: { reference_doi: '10.1371/journal.pone.0080635' },
  features_note: null,
  rows: [
    {
      rank: 1,
      code: 'I40S',
      hgvs: 'p.Ile40Ser',
      label: '40',
      sequence_position: 40,
      features: {
        author_label: '40',
        asa: 33.4,
        rsa: 0.18,
        region: 'core',
        buried_by_ligand: false,
        rsa_with_ligands: 0.18,
        distance_to_active_site: null,
      },
      filtered_by: [],
      consensus: 0.999,
      disagreement: 0.0,
      sources_scored: 2,
      cells: [
        {
          metric: 'ddg_kcal_per_mol',
          value: -0.89,
          uncertainty: 0.33,
          ci_low: -1.54,
          ci_high: -0.24,
          model_version_id: MODEL_VERSION_ID,
          model_id: 'mock_stability',
          is_mock: true,
        },
      ],
    },
  ],
}

function renderWorkbench(withRun: Run = run, withRanking: Ranking = ranking) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const clicks: string[] & { container?: HTMLElement } = []
  document.addEventListener(
    'click',
    (event) => {
      const target = event.target as HTMLElement
      clicks.push(target.closest('button,tr')?.tagName ?? target.tagName)
    },
    true,
  )

  // The same providers `app/layout.tsx` wraps the tree in, in the same order.
  // The workbench's footer mounts the design-set dialog, which uses both a
  // toast and a tooltip; rendering it with less context than the application
  // gives it would be testing a tree the user never sees.
  const view = render(
    <QueryClientProvider client={client}>
      <TooltipProvider delayDuration={300}>
        <ToastProvider>
          <Workbench
            run={withRun}
            initialRanking={withRanking}
            targetName="Luciferin 4-monooxygenase"
            apiBase="http://localhost:8000"
          />
        </ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>,
  )
  return Object.assign(clicks, { container: view.container })
}

/** The mutation cell of a row, addressed the way a user points at it. */
function cellFor(code: string): HTMLElement {
  const row = document.querySelector(`tr[data-code="${code}"]`)
  if (!row) throw new Error(`no row for ${code}`)
  const cell = row.querySelector('td:nth-child(2)') as HTMLElement
  expect(cell, 'the row must be visible to be clicked').toBeVisible()
  return cell
}

/**
 * The model version is reachable when its weights hash is *visible* — not
 * merely present in the DOM.
 *
 * The distinction is the whole test. A first attempt asserted presence, and a
 * deliberate mutation that hid the Trace control behind a disclosure — a real
 * third click for a real user — passed it, because jsdom keeps the contents of a
 * closed `<details>` in the tree. `toBeVisible` knows about closed disclosures,
 * `hidden`, `display:none` and `visibility:hidden`; presence does not.
 */
function visibleModelVersion(): HTMLElement | null {
  const matches = screen.queryAllByText(new RegExp(WEIGHTS_HASH.slice(0, 20)))
  return matches.find((node) => isVisible(node)) ?? null
}

function isVisible(node: HTMLElement): boolean {
  try {
    expect(node).toBeVisible()
    return true
  } catch {
    return false
  }
}

/** Every control the user is asked to click must be one they could actually click. */
function clickable(name: string): HTMLElement {
  const control = screen.getByRole('button', { name })
  expect(control, `"${name}" must be visible to be clicked`).toBeVisible()
  return control
}

describe('a score traces to a model version in two clicks', () => {
  beforeEach(() => {
    useWorkbench.setState({ selected: [], focused: null, anchor: null })
  })

  it('renders rows at all, so the counts below mean something', () => {
    const { container } = renderWorkbench()
    // Guards the guard: if virtualisation renders nothing in jsdom, every
    // click-count assertion below would pass because there is nothing to click.
    expect(container.querySelectorAll('tr[data-code]').length).toBeGreaterThan(0)
  })

  it('is not reachable before any click', () => {
    renderWorkbench()
    expect(visibleModelVersion()).toBeNull()
    // Nor is the control that would reveal it — the inspector is empty until a
    // variant is chosen, so there is no shortcut that skips the first click.
    expect(screen.queryByRole('button', { name: 'Trace' })).toBeNull()
    expect(screen.getByText(/Select a variant to see why/)).toBeInTheDocument()
  })

  it('is not reachable after one click', async () => {
    const user = userEvent.setup()
    const clicks = renderWorkbench()

    await user.click(cellFor('I40S'))

    expect(clicks).toHaveLength(1)
    expect(visibleModelVersion()).toBeNull()
    // The first click has to have done something, or the second would be doing
    // the work of both and the count would be a coincidence.
    expect(screen.getByRole('heading', { name: 'I40S' })).toBeInTheDocument()
  })

  it('is reachable on the second click, with everything a PI needs', async () => {
    const user = userEvent.setup()
    const clicks = renderWorkbench()

    await user.click(cellFor('I40S'))
    await user.click(clickable('Trace'))

    expect(clicks).toHaveLength(2)
    expect(visibleModelVersion()).not.toBeNull()

    // Specification §2.2: which model, which version and weights hash, which
    // inputs, which run, at what time.
    const drawer = screen.getByLabelText('Provenance')
    expect(drawer).toHaveTextContent('Mock stability predictor')
    expect(drawer).toHaveTextContent('mock_stability')
    expect(drawer).toHaveTextContent('0.1.0')
    expect(drawer).toHaveTextContent(WEIGHTS_HASH)
    expect(drawer).toHaveTextContent('score with Mock stability predictor')
    expect(drawer).toHaveTextContent('sha256:d93ab89ab420')
    expect(drawer).toHaveTextContent(run.id)
  })

  it('traces the number that was clicked, not a different one', async () => {
    const user = userEvent.setup()
    renderWorkbench()

    await user.click(cellFor('I40S'))
    await user.click(clickable('Trace'))

    const drawer = screen.getByLabelText('Provenance')
    // The value in the drawer is the value in the row.
    expect(drawer).toHaveTextContent('-0.8900')
    expect(drawer).toHaveTextContent('ddg_kcal_per_mol')
    expect(drawer).toHaveTextContent('I40S')
  })

  it('marks the traced number as synthetic in the drawer too', async () => {
    const user = userEvent.setup()
    renderWorkbench()

    await user.click(cellFor('I40S'))
    await user.click(clickable('Trace'))

    // The badge follows the number wherever it is shown, not just in the table.
    expect(screen.getByLabelText('Provenance')).toHaveTextContent('Synthetic — not model output')
  })
})

/**
 * The gate says *any* score, and the fixture above carries one. A run with two
 * predictors is the ordinary case — it is what makes the disagreement column
 * mean anything — so the count has to hold for the second score as well as the
 * first, and the second must reach its *own* model version rather than whichever
 * one the drawer happened to open on.
 *
 * Verified live in a browser on a second variant and the other metric; this is
 * the part of that run a test can keep.
 */
const FITNESS_MODEL_VERSION_ID = '4eebd010-a1cc-4fe0-aee0-b9f8afeb41bb'
const FITNESS_WEIGHTS = 'sha256:73115dbda78d974e803ada2f5ff4d87bd3b92de40606f0a7cfc1a32e8fb187eb'

const runWithBoth: Run = {
  ...run,
  config: { ...run.config, predictors: ['mock_stability', 'mock_fitness'] },
  stages: [
    ...run.stages,
    {
      id: '55555555-5555-5555-5555-555555555555',
      ordinal: 3,
      name: 'score with Mock fitness predictor',
      status: 'succeeded',
      runtime_ms: 2563,
      input_hash: 'sha256:b5e19f84ac03',
      logs: 'Wrote 10,450 scores.',
      error: null,
      model: {
        id: FITNESS_MODEL_VERSION_ID,
        model_id: 'mock_fitness',
        name: 'Mock fitness predictor',
        version: '0.1.0',
        weights_hash: FITNESS_WEIGHTS,
        modality: 'fitness',
        citation: 'No citation. Synthetic output. Not a model and not a prediction.',
        is_mock: true,
      },
    },
  ],
}

const firstRow = ranking.rows[0]!
const rankingWithBoth: Ranking = {
  ...ranking,
  metrics: [
    ...ranking.metrics,
    {
      id: 'fitness_llr',
      label: 'Fitness log-likelihood ratio',
      unit: null,
      sign_convention: 'mutant minus wild type; higher is more favourable',
      higher_is_better: true,
      reports_interval: false,
    },
  ],
  rows: [
    {
      ...firstRow,
      cells: [
        ...firstRow.cells,
        {
          metric: 'fitness_llr',
          value: 1.72,
          uncertainty: null,
          ci_low: null,
          ci_high: null,
          model_version_id: FITNESS_MODEL_VERSION_ID,
          model_id: 'mock_fitness',
          is_mock: true,
        },
      ],
    },
  ],
}

describe('"any score" means each score, not just the first', () => {
  beforeEach(() => {
    useWorkbench.setState({ selected: [], focused: null, anchor: null })
  })

  it('offers one trace per score, so neither is reachable only through the other', async () => {
    const user = userEvent.setup()
    renderWorkbench(runWithBoth, rankingWithBoth)

    await user.click(cellFor('I40S'))

    const traces = screen.getAllByRole('button', { name: 'Trace' })
    expect(traces).toHaveLength(2)
    for (const trace of traces) expect(trace).toBeVisible()
  })

  it('reaches the second score\u2019s own model version, still in two clicks', async () => {
    const user = userEvent.setup()
    const clicks = renderWorkbench(runWithBoth, rankingWithBoth)

    await user.click(cellFor('I40S'))
    const traces = screen.getAllByRole('button', { name: 'Trace' })
    await user.click(traces[1] as HTMLElement)

    expect(clicks).toHaveLength(2)

    const drawer = screen.getByLabelText('Provenance')
    // Its own model version, not the stability one the first Trace would open.
    expect(drawer).toHaveTextContent('Mock fitness predictor')
    expect(drawer).toHaveTextContent(FITNESS_WEIGHTS)
    expect(drawer).toHaveTextContent('score with Mock fitness predictor')
    expect(drawer).toHaveTextContent('fitness_llr')
    expect(drawer).not.toHaveTextContent(WEIGHTS_HASH)
  })

  it('says a point estimate has no interval rather than showing an invented one', async () => {
    const user = userEvent.setup()
    renderWorkbench(runWithBoth, rankingWithBoth)

    await user.click(cellFor('I40S'))
    await user.click(screen.getAllByRole('button', { name: 'Trace' })[1] as HTMLElement)

    // A masked-marginal log-odds ratio genuinely has no interval. Inventing one
    // at the end of the provenance trail would be worse than omitting it.
    expect(screen.getByLabelText('Provenance')).toHaveTextContent(/no interval was invented/i)
  })
})
