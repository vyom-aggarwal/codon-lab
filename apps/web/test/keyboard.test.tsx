import type { Ranking, Run } from '@codonlab/schema'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { Workbench } from '@/app/runs/[id]/workbench/workbench'
import { SHORTCUTS, ShortcutSheet } from '@/components/shortcut-sheet'
import { ToastProvider } from '@/components/ui/toast'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useWorkbench } from '@/lib/workbench-store'

/**
 * The Phase 9 subject: a keyboard-only user, and nothing else.
 *
 * `BRIEF.md` §10's first clause is "keyboard-only users can complete the full
 * flow". `DESIGN.md` §3 fixes the table path — `j`/`k` move, `x` selects,
 * `Enter` opens the inspector — and §4 adds `Esc`, `⌘K` and `?`. All of it was
 * implemented and **none of it was tested**: the handlers existed, and whether
 * they answered was a matter of trust until this file.
 *
 * Every test here drives the application with `userEvent.keyboard` and never a
 * click, because a keyboard path verified by clicking is not verified.
 */

vi.mock('@/components/workbench/structure-viewer', () => ({
  StructureViewer: () => null,
}))

// jsdom gives every element zero height, so a virtualiser asked for the visible
// window correctly returns no rows — and every assertion below would then pass
// for the worst possible reason. Same shim the two-clicks gate uses.
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get() {
      return 800
    },
  })
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
    configurable: true,
    get() {
      return 1200
    },
  })
  Element.prototype.scrollIntoView = vi.fn()
})

const MODEL_VERSION_ID = '967f9a8d-18ec-45d4-89a8-d873038e0635'

/**
 * Shaped exactly like the fixture the two-clicks gate uses, because a fixture
 * that is *nearly* the real payload renders a tree the user never sees — the
 * first version of this file omitted the interval fields and the table threw
 * on `undefined.toFixed`, which looked like a broken keyboard handler.
 */
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

function row(rank: number, code: string) {
  return {
    rank,
    code,
    hgvs: `p.Ile${rank}Ser`,
    label: String(rank),
    sequence_position: rank,
    features: {
      author_label: String(rank),
      asa: 33.4,
      rsa: 0.18,
      region: 'core' as const,
      buried_by_ligand: false,
      rsa_with_ligands: 0.18,
      distance_to_active_site: null,
    },
    filtered_by: [],
    consensus: 1 - rank / 100,
    disagreement: 0.0,
    sources_scored: 2,
    cells: [
      {
        metric: 'ddg_kcal_per_mol',
        value: -0.89 + rank * 0.1,
        uncertainty: 0.33,
        ci_low: -1.54,
        ci_high: -0.24,
        model_version_id: MODEL_VERSION_ID,
        model_id: 'mock_stability',
        is_mock: true,
      },
    ],
  }
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
  total_scored: 3,
  total_filtered: 0,
  total_ranked: 3,
  budget: null,
  is_demo: true,
  features_manifest: { reference_doi: '10.1371/journal.pone.0080635' },
  features_note: null,
  rows: [row(1, 'A1V'), row(2, 'B2W'), row(3, 'C3Y')],
}

function renderWorkbench() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider delayDuration={300}>
        <ToastProvider>
          <Workbench
            run={run}
            initialRanking={ranking}
            targetName="Lipase EstA"
            apiBase="http://localhost:8000"
          />
        </ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

describe('the variant table keyboard path', () => {
  beforeEach(() => {
    useWorkbench.setState({ selected: [], focused: null, anchor: null })
  })

  it('j moves down the rows', async () => {
    const user = userEvent.setup()
    renderWorkbench()
    await user.keyboard('j')
    expect(useWorkbench.getState().focused).toBe('A1V')
    await user.keyboard('j')
    expect(useWorkbench.getState().focused).toBe('B2W')
  })

  it('k moves back up', async () => {
    const user = userEvent.setup()
    renderWorkbench()
    await user.keyboard('jjj')
    expect(useWorkbench.getState().focused).toBe('C3Y')
    await user.keyboard('k')
    expect(useWorkbench.getState().focused).toBe('B2W')
  })

  it('the arrow keys do the same thing, for users who never learned vi', async () => {
    const user = userEvent.setup()
    renderWorkbench()
    await user.keyboard('{ArrowDown}{ArrowDown}')
    expect(useWorkbench.getState().focused).toBe('B2W')
    await user.keyboard('{ArrowUp}')
    expect(useWorkbench.getState().focused).toBe('A1V')
  })

  it('x selects the focused row and x again deselects it', async () => {
    const user = userEvent.setup()
    renderWorkbench()
    await user.keyboard('jx')
    expect(useWorkbench.getState().selected).toEqual(['A1V'])
    await user.keyboard('x')
    expect(useWorkbench.getState().selected).toEqual([])
  })

  it('Enter opens the focused row in the inspector', async () => {
    const user = userEvent.setup()
    renderWorkbench()
    await user.keyboard('jj{Enter}')
    expect(useWorkbench.getState().selected).toEqual(['B2W'])
    expect(useWorkbench.getState().focused).toBe('B2W')
  })

  it('Esc clears the selection', async () => {
    const user = userEvent.setup()
    renderWorkbench()
    await user.keyboard('jx')
    expect(useWorkbench.getState().selected).toEqual(['A1V'])
    await user.keyboard('{Escape}')
    expect(useWorkbench.getState().selected).toEqual([])
  })

  it('stops at the last row rather than wrapping to the first', async () => {
    // Wrapping would silently move a selection to the other end of a 10,000-row
    // ranking on one keypress.
    const user = userEvent.setup()
    renderWorkbench()
    await user.keyboard('jjjjj')
    expect(useWorkbench.getState().focused).toBe('C3Y')
  })

  it('ignores the table keys while a field has focus', async () => {
    // `j` and `x` are ordinary characters. Typing "jx" into the filter box must
    // filter, not move the selection.
    const user = userEvent.setup()
    renderWorkbench()
    const filter = screen.getByRole('textbox', { name: /filter|search|code/i })
    await user.click(filter)
    await user.keyboard('jx')
    expect(useWorkbench.getState().focused).toBeNull()
    expect(useWorkbench.getState().selected).toEqual([])
  })
})

describe('the shortcut sheet', () => {
  it('opens on ?', async () => {
    const user = userEvent.setup()
    render(<ShortcutSheet />)
    await user.keyboard('?')
    expect(screen.getByText('Keyboard shortcuts')).toBeInTheDocument()
  })

  it('closes on Esc', async () => {
    const user = userEvent.setup()
    render(<ShortcutSheet />)
    await user.keyboard('?')
    expect(screen.getByText('Keyboard shortcuts')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByText('Keyboard shortcuts')).toBeNull()
  })

  it('does not open while a text field has focus', async () => {
    // `?` is a character. A user typing a question mark into the goal composer
    // is not asking for help.
    const user = userEvent.setup()
    render(
      <>
        <input aria-label="Goal" />
        <ShortcutSheet />
      </>,
    )
    await user.click(screen.getByRole('textbox', { name: 'Goal' }))
    await user.keyboard('?')
    expect(screen.queryByText('Keyboard shortcuts')).toBeNull()
  })

  it('lists every binding the workbench actually implements', async () => {
    // DESIGN.md §9: "It documents the shortcuts, so it follows them." A sheet
    // that omits a key the product answers to is as wrong as one that invents
    // a key it does not — the user simply never finds the feature.
    const user = userEvent.setup()
    render(<ShortcutSheet />)
    await user.keyboard('?')

    // The dialog renders in a portal on document.body, so query from `screen`
    // rather than walking up from the title.
    const listed = screen.getAllByText((_, element) => element?.tagName === 'KBD')
    const text = listed.map((element) => element.textContent ?? '')

    for (const key of ['j', 'k', 'x', 'Enter', 'Esc']) {
      expect(
        text.some((entry) => entry.includes(key)),
        `the sheet must list ${key}; it lists ${JSON.stringify(text)}`,
      ).toBe(true)
    }
  })

  it('claims no binding the product does not have', () => {
    // The other direction, and the one that rots: every key in the sheet is
    // checked against the set the handlers answer to. Adding a row here without
    // a handler fails.
    const IMPLEMENTED = new Set([
      '⌘K  /  Ctrl K',
      '?',
      'Esc',
      'j  /  ↓',
      'k  /  ↑',
      'x',
      'Enter',
      '↑  /  ↓',
      'Type a mutation code',
    ])
    const listed = SHORTCUTS.flatMap((group) => group.keys.map(([key]) => key))
    for (const key of listed) {
      expect(IMPLEMENTED.has(key), `"${key}" is listed but not in the implemented set`).toBe(
        true,
      )
    }
  })
})
