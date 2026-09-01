import type { Filtered, Ranking, RunStage } from '@codonlab/schema'
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DemoMark } from '@/components/run/demo-mark'
import { FilteredPanel } from '@/components/run/filtered-panel'
import { RankedTable } from '@/components/run/ranked-table'
import { StageList } from '@/components/run/stage-list'

/**
 * The honesty properties of the run view, asserted rather than trusted.
 *
 * Each test here maps to a line in the specification that the interface is the
 * last place to enforce: a fabricated number carries a mark, an absent number
 * carries its reason, a sign convention is in the header, and a stage that did
 * not run still says why.
 */

const MODEL = {
  id: '00000000-0000-0000-0000-0000000000aa',
  model_id: 'mock_stability',
  name: 'Mock stability predictor',
  version: '0.1.0',
  weights_hash: 'sha256:191a9b9564b9deadbeef',
  modality: 'stability',
  citation: 'No citation. Synthetic output.',
  is_mock: true,
}

function stage(overrides: Partial<RunStage> = {}): RunStage {
  return {
    id: crypto.randomUUID(),
    ordinal: 0,
    name: 'score with Mock stability predictor',
    status: 'succeeded',
    runtime_ms: 1566,
    input_hash: 'sha256:1fba3fc6cd586325aaaa',
    logs: 'Wrote 3,439 scores.',
    error: null,
    model: MODEL,
    ...overrides,
  }
}

function ranking(overrides: Partial<Ranking> = {}): Ranking {
  return {
    run_id: '00000000-0000-0000-0000-0000000000bb',
    scheme_label: 'Mature protein, signal peptide removed',
    metrics: [
      {
        id: 'ddg_kcal_per_mol',
        label: 'Predicted ΔΔG',
        unit: 'kcal/mol',
        sign_convention: 'destabilizing positive',
        higher_is_better: false,
        reports_interval: true,
      },
      {
        id: 'fitness_llr',
        label: 'Fitness log-likelihood ratio',
        unit: null,
        sign_convention: 'mutant minus wild type; higher is more favourable',
        higher_is_better: true,
        reports_interval: false,
      },
    ],
    unavailable: {},
    total_scored: 3439,
    total_filtered: 19,
    total_ranked: 3420,
    budget: 96,
    is_demo: true,
    features_manifest: {},
    features_note: null,
    rows: [
      {
        rank: 1,
        code: 'S77A',
        hgvs: 'p.Ser77Ala',
        label: '77',
        sequence_position: 108,
        features: {
          author_label: '108',
          asa: 3.2,
          rsa: 0.02,
          region: 'core' as const,
          buried_by_ligand: false,
          rsa_with_ligands: 0.02,
          distance_to_active_site: 0.0,
        },
        filtered_by: [],
        consensus: 0.9971,
        disagreement: 0.0012,
        sources_scored: 2,
        cells: [
          {
            metric: 'ddg_kcal_per_mol',
            value: -0.74,
            uncertainty: 0.63,
            ci_low: -1.97,
            ci_high: 0.49,
            model_version_id: MODEL.id,
            model_id: 'mock_stability',
            is_mock: true,
          },
          {
            metric: 'fitness_llr',
            value: 1.46,
            uncertainty: null,
            ci_low: null,
            ci_high: null,
            model_version_id: '00000000-0000-0000-0000-0000000000cc',
            model_id: 'mock_fitness',
            is_mock: true,
          },
        ],
      },
    ],
    ...overrides,
  }
}

describe('the stage list', () => {
  it('shows model, version and weights hash on screen, not only in a log', () => {
    render(<StageList stages={[stage()]} />)
    expect(screen.getByText(/Mock stability predictor 0\.1\.0/)).toBeInTheDocument()
    expect(screen.getByText(/weights 191a9b9564b9/)).toBeInTheDocument()
  })

  it('marks a stage whose model fabricates its numbers', () => {
    render(<StageList stages={[stage()]} />)
    expect(screen.getByText('Synthetic')).toBeInTheDocument()
  })

  it('does not mark a stage whose model is real', () => {
    render(<StageList stages={[stage({ model: { ...MODEL, is_mock: false } })]} />)
    expect(screen.queryByText('Synthetic')).not.toBeInTheDocument()
  })

  it('keeps a skipped stage visible with its reason', () => {
    // A skipped stage is the explanation for a column that reads as unavailable
    // further down the page. Hiding it would remove the explanation.
    render(
      <StageList
        stages={[
          stage({
            status: 'skipped',
            logs: 'This predictor requires a structure and none is attached.',
          }),
        ]}
      />,
    )
    expect(screen.getByText('skipped')).toBeInTheDocument()
    expect(screen.getByText(/requires a structure/)).toBeInTheDocument()
  })

  it('puts logs behind a disclosure rather than on the page', () => {
    render(<StageList stages={[stage()]} />)
    expect(screen.getByText('Logs').tagName.toLowerCase()).toBe('summary')
  })

  it('renders a missing runtime as an em dash, never as zero', () => {
    render(<StageList stages={[stage({ status: 'pending', runtime_ms: null })]} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})

describe('the ranked table', () => {
  it('states the unit and sign convention in the column header', () => {
    render(<RankedTable ranking={ranking()} />)
    expect(screen.getByText(/kcal\/mol · destabilizing positive/)).toBeInTheDocument()
  })

  it('names the numbering scheme beside the mutation column', () => {
    render(<RankedTable ranking={ranking()} />)
    expect(
      screen.getByText('Mature protein, signal peptide removed'),
    ).toBeInTheDocument()
  })

  it('renders the mutation code in both forms', () => {
    render(<RankedTable ranking={ranking()} />)
    expect(screen.getByText(/S77A/)).toBeInTheDocument()
    expect(screen.getByText(/p\.Ser77Ala/)).toBeInTheDocument()
  })

  it('marks every individual number a mock produced', () => {
    render(<RankedTable ranking={ranking()} />)
    const row = screen.getByText(/S77A/).closest('tr')
    expect(row).not.toBeNull()
    // Two numbers from a fabricating provider, so two marks — not one badge for
    // the row and not one for the page.
    expect(within(row as HTMLElement).getAllByLabelText('synthetic value')).toHaveLength(2)
  })

  it('leaves real numbers unmarked', () => {
    const real = ranking()
    const row = real.rows[0]!
    render(
      <RankedTable
        ranking={{
          ...real,
          rows: [{ ...row, cells: row.cells.map((cell) => ({ ...cell, is_mock: false })) }],
        }}
      />,
    )
    expect(screen.queryAllByLabelText('synthetic value')).toHaveLength(0)
  })

  it('shows an interval for a metric that reports one', () => {
    render(<RankedTable ranking={ranking()} />)
    expect(screen.getByText('-0.74 ± 0.63')).toBeInTheDocument()
  })

  it('shows no interval for a point-estimate metric rather than inventing one', () => {
    render(<RankedTable ranking={ranking()} />)
    const cell = screen.getByText('1.46')
    expect(cell).toBeInTheDocument()
    expect(cell.getAttribute('title')).toMatch(/point estimate/)
  })

  it('renders a missing number as an em dash carrying its reason', () => {
    const base = ranking()
    const row = base.rows[0]!
    render(
      <RankedTable
        ranking={{
          ...base,
          unavailable: {
            ddg_kcal_per_mol: 'Mock stability predictor: requires a structure and none is attached.',
          },
          rows: [
            {
              ...row,
              cells: row.cells.filter((cell) => cell.metric !== 'ddg_kcal_per_mol'),
              sources_scored: 1,
              disagreement: null,
            },
          ],
        }}
      />,
    )
    const dash = screen.getAllByText('—')[0]
    expect(dash).toBeInTheDocument()
    expect(dash?.getAttribute('title')).toMatch(/requires a structure/)
  })

  it('reports no disagreement rather than zero when only one predictor scored', () => {
    const base = ranking()
    const row = base.rows[0]!
    render(
      <RankedTable
        ranking={{ ...base, rows: [{ ...row, disagreement: null, sources_scored: 1 }] }}
      />,
    )
    const dashes = screen.getAllByText('—')
    expect(dashes.some((node) => /nothing to disagree/.test(node.getAttribute('title') ?? ''))).toBe(
      true,
    )
  })

  it('does not round a real disagreement down to unanimity', () => {
    render(<RankedTable ranking={ranking()} />)
    expect(screen.getByText('0.001')).toBeInTheDocument()
  })

  it('says the consensus is a rank and not a physical quantity', () => {
    render(<RankedTable ranking={ranking()} />)
    expect(screen.getByText(/not a physical quantity/)).toBeInTheDocument()
  })
})

describe('the constraint filter', () => {
  function filtered(overrides: Partial<Filtered> = {}): Filtered {
    return {
      run_id: '00000000-0000-0000-0000-0000000000bb',
      override: false,
      kept: 3420,
      removed: { S77A: ['catalytic'], S77C: ['catalytic'] },
      constrained_positions: { '108': ['catalytic'] },
      ...overrides,
    }
  }

  it('keeps every removed variant retrievable with the reason shown', () => {
    render(<FilteredPanel filtered={filtered()} />)
    expect(screen.getByText('S77A')).toBeInTheDocument()
    expect(screen.getAllByText('catalytic')).toHaveLength(2)
  })

  it('says plainly when nothing was removed', () => {
    render(<FilteredPanel filtered={filtered({ removed: {} })} />)
    expect(screen.getByText(/No variant was removed/)).toBeInTheDocument()
  })

  it('makes an override unmissable', () => {
    render(<FilteredPanel filtered={filtered({ override: true })} />)
    expect(screen.getByText(/Constraints overridden/)).toBeInTheDocument()
    expect(screen.getByText(/recorded in the provenance trail/)).toBeInTheDocument()
  })
})

describe('the demo mark', () => {
  it('carries its explanation without needing the footnote', () => {
    render(<DemoMark modelName="mock_stability" />)
    const mark = screen.getByLabelText('synthetic value')
    expect(mark.getAttribute('title')).toMatch(/Not model output/)
    expect(mark.getAttribute('title')).toMatch(/mock_stability/)
  })
})
