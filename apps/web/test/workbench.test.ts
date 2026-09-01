import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import type { RankedVariant, Ranking } from '@codonlab/schema'
import { describe, expect, it } from 'vitest'

import { rationaleFor } from '@/lib/rationale'
import { applyFilters, regionCounts } from '@/lib/workbench-filter'
import { ROW_HEIGHT, ROW_HEIGHT_COMPACT } from '@/components/workbench/variant-table'
import type { Filters } from '@/lib/workbench-store'

/**
 * The workbench's pure parts: the row geometry virtualisation depends on, the
 * filter predicate, and the rationale paragraph.
 *
 * The rationale tests are the important ones. Specification §5.6 requires it to
 * be derived from actual feature values rather than written by a language model,
 * and the way that requirement fails quietly is a sentence that sounds
 * reasonable and is not backed by a number. Every assertion below ties a clause
 * to the field it must have come from.
 */

const REPO_ROOT = join(import.meta.dirname, '..', '..', '..')

function variant(overrides: Partial<RankedVariant> = {}): RankedVariant {
  return {
    rank: 1,
    code: 'S77A',
    hgvs: 'p.Ser77Ala',
    label: '77',
    sequence_position: 108,
    features: {
      author_label: '108',
      asa: 3.2,
      rsa: 0.02,
      region: 'core',
      buried_by_ligand: false,
      rsa_with_ligands: 0.02,
      distance_to_active_site: 4.3,
    },
    filtered_by: [],
    consensus: 0.9,
    disagreement: 0.1,
    sources_scored: 2,
    cells: [
      {
        metric: 'ddg_kcal_per_mol',
        value: -0.74,
        uncertainty: 0.63,
        ci_low: -1.97,
        ci_high: 0.49,
        model_version_id: '00000000-0000-0000-0000-0000000000aa',
        model_id: 'mock_stability',
        is_mock: true,
      },
    ],
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
    ],
    unavailable: {},
    total_scored: 100,
    total_filtered: 0,
    total_ranked: 100,
    budget: null,
    is_demo: true,
    rows: [],
    features_manifest: { reference_doi: '10.1371/journal.pone.0080635' },
    features_note: null,
    ...overrides,
  }
}

const NO_FILTERS: Filters = {
  query: '',
  regions: ['core', 'boundary', 'surface', 'unmeasured'],
  maxDistance: null,
  onlyBuriedByLigand: false,
  includeRemoved: false,
}

describe('row geometry', () => {
  it('matches the row heights DESIGN.md states', () => {
    // Virtualisation needs the row height as a number, which duplicates a token
    // into JavaScript. This is the check that keeps the copy honest.
    const design = readFileSync(join(REPO_ROOT, 'DESIGN.md'), 'utf8')
    const row = /`--spacing-row`\s*\|\s*`(\d+)px`/.exec(design)
    const compact = /`--spacing-row-compact`\s*\|\s*`(\d+)px`/.exec(design)
    expect(row?.[1]).toBeDefined()
    expect(Number(row?.[1])).toBe(ROW_HEIGHT)
    expect(Number(compact?.[1])).toBe(ROW_HEIGHT_COMPACT)
  })
})

describe('filters', () => {
  const rows = [
    variant({ code: 'S77A', features: { ...variant().features, region: 'core' } }),
    variant({
      code: 'L120K',
      features: {
        ...variant().features,
        region: 'surface',
        distance_to_active_site: 18.2,
      },
    }),
    variant({
      code: 'G9P',
      features: {
        ...variant().features,
        region: null,
        rsa: null,
        distance_to_active_site: null,
      },
    }),
  ]

  it('matches mutation codes case-insensitively', () => {
    expect(applyFilters(rows, { ...NO_FILTERS, query: 's77' }).map((r) => r.code)).toEqual([
      'S77A',
    ])
  })

  it('counts a variant with no measured geometry as unmeasured, not as surface', () => {
    expect(regionCounts(rows)).toEqual({ core: 1, boundary: 0, surface: 1, unmeasured: 1 })
  })

  it('excludes a variant with no measured distance rather than assuming one', () => {
    const near = applyFilters(rows, { ...NO_FILTERS, maxDistance: 10 })
    expect(near.map((r) => r.code)).toEqual(['S77A'])
  })

  it('region toggles remove exactly their own rows', () => {
    const withoutCore = applyFilters(rows, {
      ...NO_FILTERS,
      regions: ['boundary', 'surface', 'unmeasured'],
    })
    expect(withoutCore).toHaveLength(2)
  })
})

describe('the rationale', () => {
  it('states the burial class with the number it came from', () => {
    const clauses = rationaleFor(variant(), ranking())
    const rsa = clauses.find((clause) => clause.source === 'RSA')
    expect(rsa?.text).toContain('core')
    expect(rsa?.text).toContain('0.02')
  })

  it('names the engineering strategy the region implies, not a verdict', () => {
    const core = rationaleFor(variant(), ranking()).find((c) => c.source === 'RSA')
    expect(core?.text).toContain('packing')
    const surface = rationaleFor(
      variant({ features: { ...variant().features, region: 'surface', rsa: 0.62 } }),
      ranking(),
    ).find((c) => c.source === 'RSA')
    expect(surface?.text).toContain('surface chemistry')
  })

  it('says nothing about burial when nothing was measured', () => {
    const bare = variant({
      features: {
        author_label: null,
        asa: null,
        rsa: null,
        region: null,
        buried_by_ligand: false,
        rsa_with_ligands: null,
        distance_to_active_site: null,
      },
    })
    const clauses = rationaleFor(bare, ranking({ features_note: 'No structure attached.' }))
    expect(clauses.some((clause) => clause.source === 'RSA')).toBe(false)
    // And it says why, rather than leaving a gap the reader has to interpret.
    expect(clauses.find((c) => c.source === 'Geometry')?.text).toBe('No structure attached.')
  })

  it('flags a residue the cofactor buries as a caution', () => {
    const clauses = rationaleFor(
      variant({
        features: {
          ...variant().features,
          region: 'surface',
          rsa: 0.55,
          buried_by_ligand: true,
          rsa_with_ligands: 0.2,
        },
      }),
      ranking(),
    )
    const cofactor = clauses.find((clause) => clause.source === 'Cofactor')
    expect(cofactor?.caution).toBe(true)
    expect(cofactor?.text).toContain('0.20')
  })

  it('warns when a substitution is close enough to reach the active site', () => {
    const near = rationaleFor(variant(), ranking()).find((c) => c.source === 'Active site')
    expect(near?.caution).toBe(true)
    expect(near?.text).toContain('4.3')
    const far = rationaleFor(
      variant({ features: { ...variant().features, distance_to_active_site: 22.0 } }),
      ranking(),
    ).find((c) => c.source === 'Active site')
    expect(far?.caution).toBe(false)
  })

  it('carries each score with its own sign convention', () => {
    const clause = rationaleFor(variant(), ranking()).find((c) => c.source === 'mock_stability')
    expect(clause?.text).toContain('-0.74')
    expect(clause?.text).toContain('destabilizing positive')
    expect(clause?.text).toContain('95% interval')
  })

  it('calls out sharp disagreement rather than presenting a ranking as settled', () => {
    const clause = rationaleFor(variant({ disagreement: 0.8 }), ranking()).find(
      (c) => c.source === 'Agreement',
    )
    expect(clause?.caution).toBe(true)
    expect(clause?.text).toContain('weak evidence')
  })

  it('does not claim agreement when only one predictor scored the variant', () => {
    const clause = rationaleFor(
      variant({ sources_scored: 1, disagreement: null }),
      ranking(),
    ).find((c) => c.source === 'Agreement')
    expect(clause?.text).toContain('no agreement to report')
  })

  it('always states the limits of the run, whatever the numbers say', () => {
    const clauses = rationaleFor(variant(), ranking())
    expect(clauses.find((c) => c.source === 'Demo')?.caution).toBe(true)
    expect(clauses.find((c) => c.source === 'Conservation')?.text).toContain('MSA')
    // Specification §7: never claim a Tm shift from a stability prediction.
    expect(clauses.find((c) => c.source === 'Scope')?.text).toContain('melting temperature')
  })

  it('drops the synthetic warning when the numbers are real', () => {
    const clauses = rationaleFor(variant(), ranking({ is_demo: false }))
    expect(clauses.some((c) => c.source === 'Demo')).toBe(false)
  })

  it('never invents a number that is not on the row', () => {
    // Every numeral in the composed text must appear in the row's own data.
    const row = variant()
    const text = rationaleFor(row, ranking())
      .filter((clause) => ['RSA', 'Active site', 'mock_stability'].includes(clause.source))
      .map((clause) => clause.text)
      .join(' ')
    const known = new Set(['0.02', '4.3', '-0.74', '0.63', '-1.97', '0.49', '95'])
    for (const numeral of text.match(/-?\d+\.?\d*/g) ?? []) {
      expect(known.has(numeral), `${numeral} is not a value on the row`).toBe(true)
    }
  })
})
