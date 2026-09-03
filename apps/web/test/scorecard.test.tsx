import type { Scorecard } from '@codonlab/schema'
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ScorecardCard } from '@/components/scorecard/scorecard-card'
import { ScorecardView } from '@/components/scorecard/scorecard-view'

/**
 * The scorecard's shape is a contract, not a layout preference.
 *
 * `ARCHITECTURE.md` §13: "The bias term is rendered visually adjacent to the
 * rank term, not in a detail panel or behind a tab. A predictor that ranks
 * perfectly and sits 2 kcal/mol high must show both facts in one glance, or the
 * scorecard has failed at the only job it has."
 *
 * A comment saying so is not enforcement. These tests assert the adjacency from
 * the rendered DOM, so moving the bias figure into a tab, a disclosure or a
 * second card fails the build.
 */

function card(overrides: Partial<Scorecard> = {}): Scorecard {
  return {
    model_id: 'thermompnn',
    model_name: 'ThermoMPNN',
    model_version: 'v1.0.0',
    weights_hash: 'sha256:2b04fd370e399911b1fa5848112cc9013f084110',
    model_version_id: '00000000-0000-0000-0000-0000000000aa',
    is_mock: false,
    predicted_metric: 'ddg_kcal_per_mol',
    predicted_unit: 'kcal/mol',
    predicted_sign: 'destabilizing positive',
    measured_metric: 'ddg_kcal_per_mol',
    measured_unit: 'kcal/mol',
    measured_sign: 'lower is better',
    n: 120,
    spearman: 1.0,
    precision_k: 10,
    precision: 1.0,
    mae: 2.0,
    mean_signed_error: 2.0,
    error_unit: 'kcal/mol',
    bias_note: 'Predicted minus measured, in kcal/mol. Positive means the predictor reads high.',
    error_unavailable_reason: '',
    precision_note: '',
    calibration: [
      { predicted: 2.5, measured: 0.5, count: 40 },
      { predicted: 3.5, measured: 1.5, count: 40 },
      { predicted: 4.5, measured: 2.5, count: 40 },
    ],
    points: [
      { variant_id: '00000000-0000-0000-0000-000000000001', code: 'A1V', hgvs: 'p.Ala1Val', predicted: 2.5, measured: 0.5, replicates: 1 },
      { variant_id: '00000000-0000-0000-0000-000000000002', code: 'A2V', hgvs: 'p.Ala2Val', predicted: 3.5, measured: 1.5, replicates: 1 },
      { variant_id: '00000000-0000-0000-0000-000000000003', code: 'A3V', hgvs: 'p.Ala3Val', predicted: 4.5, measured: 2.5, replicates: 2 },
    ],
    targets: ['Lipase EstA'],
    target_count: 1,
    ...overrides,
  }
}

/** The predictor §13 describes: perfectly ordered, two units high. */
const OFFSET_BY_TWO = card()

describe('a rank statistic never stands alone', () => {
  it('shows the bias term in the same figure row as the rank terms', () => {
    render(<ScorecardCard card={OFFSET_BY_TWO} />)

    const rank = screen.getByText('Spearman ρ')
    const bias = screen.getByText('Mean signed error (kcal/mol)')

    // Both are <dt> elements inside one <dl>. A tab, a disclosure or a second
    // card would break this, which is the point.
    const rankList = rank.closest('dl')
    const biasList = bias.closest('dl')
    expect(rankList).not.toBeNull()
    expect(biasList).toBe(rankList)
  })

  it('puts rank, error and bias in one row in that order', () => {
    render(<ScorecardCard card={OFFSET_BY_TWO} />)
    const terms = Array.from(
      screen.getByText('Spearman ρ').closest('dl')!.querySelectorAll('dt'),
    ).map((node) => node.textContent)

    expect(terms).toEqual([
      'Spearman ρ',
      'Precision@10',
      'MAE (kcal/mol)',
      'Mean signed error (kcal/mol)',
    ])
  })

  it('reports the perfect rank and the two-unit bias together', () => {
    render(<ScorecardCard card={OFFSET_BY_TWO} />)
    const figures = screen.getByText('Spearman ρ').closest('dl')!

    expect(within(figures).getByText('1.000')).toBeInTheDocument()
    expect(within(figures).getByText('1.00')).toBeInTheDocument()
    expect(within(figures).getByText('2.00')).toBeInTheDocument()
    expect(within(figures).getByText('+2.00')).toBeInTheDocument()
  })

  it('renders no bias figure without a sign', () => {
    render(<ScorecardCard card={card({ mean_signed_error: -1.25 })} />)
    expect(screen.getByText('-1.25')).toBeInTheDocument()
  })

  it('states which direction a positive bias means', () => {
    render(<ScorecardCard card={OFFSET_BY_TWO} />)
    expect(screen.getByText(/reads high/)).toBeInTheDocument()
  })
})

describe('an uncomputable error says so, in the same block', () => {
  const rankOnly = card({
    measured_metric: 't50_celsius',
    measured_unit: '°C',
    measured_sign: 'higher is better',
    mae: null,
    mean_signed_error: null,
    error_unit: null,
    bias_note: '',
    calibration: [],
    error_unavailable_reason:
      'Predicted ddg_kcal_per_mol is in kcal/mol and measured t50_celsius is in °C. ' +
      'These are not the same quantity, so an absolute error between them would not mean ' +
      'anything. No conversion is applied.',
  })

  it('renders an em dash rather than a zero', () => {
    render(<ScorecardCard card={rankOnly} />)
    const figures = screen.getByText('Spearman ρ').closest('dl')!
    expect(within(figures).getAllByText('—').length).toBe(2)
    expect(within(figures).queryByText('0.00')).toBeNull()
  })

  it('prints the reason on the card, not in a tooltip', () => {
    render(<ScorecardCard card={rankOnly} />)
    // getByText matches rendered text content; a title attribute would not
    // satisfy it, which is the property being asserted. The reason appears
    // twice on purpose — once beside the figures, once where the calibration
    // curve would have been — so this is getAllByText rather than getByText.
    expect(screen.getByText(/No error or bias figure for this pair/)).toBeInTheDocument()
    expect(screen.getAllByText(/not the same quantity/).length).toBeGreaterThan(0)
  })

  it('says what a rank statistic alone does and does not establish', () => {
    render(<ScorecardCard card={rankOnly} />)
    expect(
      screen.getByText(/says only whether the ordering is right, not whether the numbers are/),
    ).toBeInTheDocument()
  })

  it('still shows the rank figures, which are legitimately computable', () => {
    render(<ScorecardCard card={rankOnly} />)
    const figures = screen.getByText('Spearman ρ').closest('dl')!
    expect(within(figures).getByText('1.000')).toBeInTheDocument()
  })

  it('explains the missing calibration curve instead of drawing an empty frame', () => {
    render(<ScorecardCard card={rankOnly} />)
    expect(screen.getByText(/compares absolute values/)).toBeInTheDocument()
  })
})

describe('provenance and honesty marks', () => {
  it('badges a card built on a fabricating predictor', () => {
    render(<ScorecardCard card={card({ is_mock: true })} />)
    expect(screen.getByText(/Synthetic predictor/)).toBeInTheDocument()
  })

  it('does not badge a card built on a real predictor', () => {
    render(<ScorecardCard card={card({ is_mock: false })} />)
    expect(screen.queryByText(/Synthetic predictor/)).toBeNull()
  })

  it('names the weights the numbers came from', () => {
    render(<ScorecardCard card={OFFSET_BY_TWO} />)
    // Truncated for the footer, so the assertion matches the prefix actually
    // rendered rather than the full hash.
    expect(screen.getByText(/^sha256:2b04fd370/)).toBeInTheDocument()
  })

  it('states both sign conventions being compared', () => {
    render(<ScorecardCard card={OFFSET_BY_TWO} />)
    expect(screen.getByText(/destabilizing positive/)).toBeInTheDocument()
    expect(screen.getByText(/lower is better/)).toBeInTheDocument()
  })

  it('says how many variants the card rests on', () => {
    render(<ScorecardCard card={OFFSET_BY_TWO} />)
    expect(screen.getByText(/120 variants with both a prediction and a measurement/))
      .toBeInTheDocument()
  })
})

describe('precision@k that cannot be asked', () => {
  it('shows the reason rather than a scaled number', () => {
    render(
      <ScorecardCard
        card={card({
          n: 6,
          precision: null,
          precision_note:
            'precision@10 needs at least 10 variants with both a prediction and a measurement; there are 6.',
        })}
      />,
    )
    expect(screen.getByText(/needs at least 10 variants/)).toBeInTheDocument()
  })
})

describe('empty states name the next action', () => {
  it('explains an empty scorecard rather than showing a blank page', () => {
    render(
      <ScorecardView
        scope="Lipase EstA"
        targetId="00000000-0000-0000-0000-0000000000cc"
        report={{
          cards: [],
          note: 'Measured values are joined to variants, but no active predictor has scored those variants yet. Run a design run over this target to compare against.',
          measured_variants: 2172,
          unjoined_measurements: 0,
          metrics: ['t50_celsius'],
          is_demo: false,
        }}
      />,
    )
    expect(screen.getByText(/Run a design run over this target/)).toBeInTheDocument()
  })

  it('reports unjoined rows as kept rather than discarded', () => {
    render(
      <ScorecardView
        scope="Lipase EstA"
        report={{
          cards: [card()],
          note: '',
          measured_variants: 120,
          unjoined_measurements: 7,
          metrics: ['ddg_kcal_per_mol'],
          is_demo: false,
        }}
      />,
    )
    expect(screen.getByText(/They were kept, not discarded/)).toBeInTheDocument()
  })
})
