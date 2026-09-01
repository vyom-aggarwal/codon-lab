import type { Metric, RankedVariant, Ranking } from '@codonlab/schema'

/**
 * Why this variant was proposed, composed from the values that actually exist.
 *
 * Specification §5.6 asks for a plain-language paragraph "derived from the
 * actual feature values (not from an LLM guessing)". This is that function: it
 * is a pure transformation of numbers already on the row, so every clause can be
 * checked against a column, and a feature that was not measured produces no
 * sentence rather than a hedge.
 *
 * It never says a variant is good. It says what is true about it, including the
 * parts that argue against it.
 */

export interface RationaleClause {
  /** Short label for the fact this clause rests on, shown beside it. */
  source: string
  text: string
  /** True when the clause is a caution rather than an observation. */
  caution?: boolean
}

function metricFor(ranking: Ranking, id: string): Metric | undefined {
  return ranking.metrics.find((metric) => metric.id === id)
}

function describeRegion(row: RankedVariant): RationaleClause | null {
  const { region, rsa } = row.features
  if (region === null || rsa === null) return null

  const strategy =
    region === 'core'
      ? 'Substitutions here act on packing, not on surface chemistry.'
      : region === 'surface'
        ? 'Substitutions here act on surface chemistry, not on packing.'
        : 'It sits between the two, where both packing and surface effects apply.'

  return {
    source: 'RSA',
    text: `Buried class ${region}, from a relative solvent accessibility of ${rsa.toFixed(2)}. ${strategy}`,
  }
}

function describeLigandBurial(row: RankedVariant): RationaleClause | null {
  const { buried_by_ligand, rsa, rsa_with_ligands } = row.features
  if (!buried_by_ligand || rsa === null || rsa_with_ligands === null) return null
  return {
    source: 'Cofactor',
    caution: true,
    text:
      `The accessibility above is for the protein alone. With cofactors present this ` +
      `residue drops to ${rsa_with_ligands.toFixed(2)}, so treating it as exposed would be wrong.`,
  }
}

function describeDistance(row: RankedVariant): RationaleClause | null {
  const distance = row.features.distance_to_active_site
  if (distance === null) return null
  return {
    source: 'Active site',
    caution: distance < 8,
    text:
      `${distance.toFixed(1)} A from the annotated active site, measured between closest ` +
      `non-hydrogen atoms.` +
      (distance < 8 ? ' Close enough that a side-chain change may reach into it.' : ''),
  }
}

function describeScores(row: RankedVariant, ranking: Ranking): RationaleClause[] {
  return row.cells.map((cell) => {
    const metric = metricFor(ranking, cell.metric)
    const label = metric?.label ?? cell.metric
    const unit = metric?.unit ? ` ${metric.unit}` : ''
    const interval =
      metric?.reports_interval && cell.ci_low !== null && cell.ci_high !== null
        ? ` (95% interval ${cell.ci_low.toFixed(2)} to ${cell.ci_high.toFixed(2)})`
        : ''
    const direction = metric
      ? metric.higher_is_better
        ? 'higher is more favourable'
        : metric.sign_convention
      : ''
    return {
      source: cell.model_id,
      text: `${label} ${cell.value.toFixed(2)}${unit}${interval} — ${direction}.`,
    }
  })
}

function describeAgreement(row: RankedVariant): RationaleClause | null {
  if (row.sources_scored < 2 || row.disagreement === null) {
    return {
      source: 'Agreement',
      text: 'Only one predictor scored this variant, so there is no agreement to report.',
    }
  }
  const spread = row.disagreement
  return {
    source: 'Agreement',
    caution: spread > 0.5,
    text:
      spread > 0.5
        ? `The predictors disagree sharply about this variant (rank spread ${spread.toFixed(2)} of a possible 1.00). Treat the ranking as weak evidence here.`
        : `The predictors broadly agree about this variant (rank spread ${spread.toFixed(2)} of a possible 1.00).`,
  }
}

/**
 * The clauses that always apply, whatever the numbers say. These are the limits
 * of the run, not of the variant, and they are stated every time rather than
 * left for the reader to remember.
 */
function describeLimits(ranking: Ranking): RationaleClause[] {
  const clauses: RationaleClause[] = []
  if (ranking.is_demo) {
    clauses.push({
      source: 'Demo',
      caution: true,
      text:
        'Every score above is synthetic, produced by a provider that fabricates numbers. ' +
        'Nothing here is a prediction.',
    })
  }
  clauses.push({
    source: 'Conservation',
    text:
      'Evolutionary conservation was not measured — no MSA provider is configured — so ' +
      'the high-risk flag for highly conserved positions is not available.',
  })
  clauses.push({
    source: 'Scope',
    text:
      'A stability change is a change in folding free energy. It does not convert to a ' +
      'melting temperature, and this ranking is a hypothesis until it is measured.',
  })
  return clauses
}

export function rationaleFor(row: RankedVariant, ranking: Ranking): RationaleClause[] {
  const clauses: RationaleClause[] = []
  const region = describeRegion(row)
  if (region) clauses.push(region)

  const ligand = describeLigandBurial(row)
  if (ligand) clauses.push(ligand)

  const distance = describeDistance(row)
  if (distance) clauses.push(distance)

  if (!region && !distance) {
    clauses.push({
      source: 'Geometry',
      text:
        ranking.features_note ??
        'No structural geometry was measured for this run, so nothing can be said about ' +
          'burial or proximity to the active site.',
    })
  }

  clauses.push(...describeScores(row, ranking))
  const agreement = describeAgreement(row)
  if (agreement) clauses.push(agreement)
  clauses.push(...describeLimits(ranking))
  return clauses
}
