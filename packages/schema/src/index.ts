/**
 * The contract between apps/web and apps/api.
 *
 * Hand-written for now. Once the API surface grows past a couple of endpoints
 * these move to generation from the FastAPI OpenAPI document, so the Pydantic
 * models stay the single source of truth and drift becomes impossible rather
 * than merely unlikely.
 */

import { z } from 'zod'

/**
 * A predictor as data. Everything the interface varies by model comes from
 * here — never from naming a model in a component. See ARCHITECTURE.md §2.
 */
export const predictorSchema = z.object({
  id: z.string(),
  name: z.string(),
  version: z.string(),
  weights_hash: z.string(),
  modality: z.string(),
  citation: z.string(),
  is_mock: z.boolean(),
  /** False when the runtime or the weights are missing. It never falls back. */
  available: z.boolean().default(true),
  unavailable_reason: z.string().nullable().default(null),
  objectives: z.array(z.string()),
  requires: z.object({
    structure: z.boolean(),
    msa: z.boolean(),
    max_length: z.number().int().nullable(),
    gpu: z.boolean(),
  }),
  metrics: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
      unit: z.string().nullable(),
      /** Stated in the column header, and never changed. */
      sign_convention: z.string(),
      higher_is_better: z.boolean(),
      reports_interval: z.boolean(),
    }),
  ),
})

export type Predictor = z.infer<typeof predictorSchema>

/** Why a queued run is not moving. Two causes, both invisible from the run. */
export const queueSchema = z.object({
  connected: z.boolean(),
  workers: z.number().int(),
  queued: z.number().int(),
  detail: z.string().nullable(),
})

export type QueueStatus = z.infer<typeof queueSchema>

/**
 * Demo mode is the honesty switch. When true, a provider that fabricates numbers
 * is active and the interface must say so on every screen. The API derives it
 * from the predictors themselves, so it cannot drift from what is running.
 */
export const metaSchema = z.object({
  demo_mode: z.boolean(),
  providers: z.array(z.string()),
  predictors: z.array(predictorSchema),
  /** Objectives no active predictor supports are greyed out in the composer. */
  supported_objectives: z.array(z.string()),
  unknown_providers: z.array(z.string()),
  /**
   * Per objective: whether anything runnable covers it, and if not, the reason.
   * The composer greys an objective out *with* its explanation — silence would
   * leave a scientist guessing whether the tool is broken or the question is out
   * of scope.
   */
  objective_support: z
    .record(
      z.string(),
      z.object({
        supported: z.boolean(),
        predictors: z.array(z.string()),
        reason: z.string().nullable(),
      }),
    )
    .default({}),
  queue: queueSchema,
})

export type Meta = z.infer<typeof metaSchema>

export const projectRowSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  organism: z.string().nullable(),
  objective: z.string().nullable(),
  target_name: z.string().nullable(),
  target_count: z.number().int(),
  run_count: z.number().int(),
  measured_variant_count: z.number().int(),
  last_activity_at: z.string().datetime({ offset: true }).nullable(),
  created_at: z.string().datetime({ offset: true }),
})

export type ProjectRow = z.infer<typeof projectRowSchema>

export const projectListSchema = z.array(projectRowSchema)

/** Numbering scheme kinds, mirroring `codonlab.models.enums.NumberingKind`. */
export const numberingKindSchema = z.enum(['sequence', 'pdb_author', 'construct'])
export type NumberingKind = z.infer<typeof numberingKindSchema>

export const numberingSchemeSchema = z.object({
  id: z.string().uuid(),
  kind: numberingKindSchema,
  label: z.string(),
  is_canonical: z.boolean(),
  note: z.string().nullable(),
  first_label: z.string().nullable(),
  last_label: z.string().nullable(),
  covered: z.number().int(),
})

export type NumberingScheme = z.infer<typeof numberingSchemeSchema>

export const structureSchema = z.object({
  id: z.string().uuid(),
  source: z.string(),
  identifier: z.string().nullable(),
  chain: z.string().nullable(),
  content_hash: z.string(),
  is_predicted: z.boolean(),
})

export type Structure = z.infer<typeof structureSchema>

export const targetSchema = z.object({
  id: z.string().uuid(),
  project_id: z.string().uuid(),
  name: z.string(),
  organism: z.string().nullable(),
  uniprot_accession: z.string().nullable(),
  sequence: z.string(),
  length: z.number().int(),
  numbering_schemes: z.array(numberingSchemeSchema),
  structures: z.array(structureSchema),
  canonical_scheme_label: z.string().nullable(),
  /** False until a canonical scheme is confirmed. Gates every downstream screen. */
  is_designable: z.boolean(),
})

export type Target = z.infer<typeof targetSchema>

export const targetSummarySchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  organism: z.string().nullable(),
  uniprot_accession: z.string().nullable(),
  length: z.number().int(),
  is_designable: z.boolean(),
  canonical_scheme_label: z.string().nullable(),
})

/** Where core stops and surface starts. A project-level scientific setting. */
export const rsaCutoffsSchema = z.object({
  core_max: z.number(),
  surface_min: z.number(),
})

export type RsaCutoffs = z.infer<typeof rsaCutoffsSchema>

export const projectDetailSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  organism: z.string().nullable(),
  objective: z.string().nullable(),
  created_at: z.string().datetime({ offset: true }),
  targets: z.array(targetSummarySchema),
  rsa_cutoffs: rsaCutoffsSchema,
})

export type ProjectDetail = z.infer<typeof projectDetailSchema>
export type TargetSummary = z.infer<typeof targetSummarySchema>

export const reconcileOutcomeSchema = z.enum(['reconciled', 'ambiguous', 'needs_alignment'])
export type ReconcileOutcome = z.infer<typeof reconcileOutcomeSchema>

export const mismatchSchema = z.object({
  sequence_position: z.number().int(),
  sequence_residue: z.string(),
  structure_label: z.string(),
  structure_residue: z.string(),
})

export const reconciliationSchema = z.object({
  outcome: reconcileOutcomeSchema,
  method: z.enum(['exact', 'alignment']).nullable(),
  chain_id: z.string(),
  structure_id: z.string().uuid(),
  coverage: z.number(),
  identity: z.number(),
  covered: z.number().int(),
  total: z.number().int(),
  mismatches: z.array(mismatchSchema),
  candidate_offsets: z.array(z.number().int()),
  /** Present only when an alignment ran. Stated so the run is reproducible. */
  parameters: z.record(z.string(), z.number()).nullable(),
  note: z.string(),
  labels: z.array(z.string().nullable()),
})

export type Reconciliation = z.infer<typeof reconciliationSchema>
export type Mismatch = z.infer<typeof mismatchSchema>

export const trackResidueSchema = z.object({
  index: z.number().int(),
  residue: z.string(),
  label: z.string().nullable(),
})

export const sequenceTrackSchema = z.object({
  target_id: z.string().uuid(),
  scheme_label: z.string().nullable(),
  residues: z.array(trackResidueSchema),
  schemes: z.array(z.record(z.string(), z.unknown())),
})

export type SequenceTrack = z.infer<typeof sequenceTrackSchema>
export type TrackResidue = z.infer<typeof trackResidueSchema>

/* ------------------------------------------------------------------ goals */

export const objectiveSchema = z.enum([
  'thermostability',
  'activity',
  'expression',
  'solubility',
  'binding_affinity',
  'specificity',
  'solvent_tolerance',
  'other',
])

export type Objective = z.infer<typeof objectiveSchema>

/**
 * Every field is nullable. An absent field means the user did not state it —
 * never a default. The UI must render "not stated" rather than filling a gap.
 */
export const goalSpecSchema = z.object({
  objective: objectiveSchema.nullable(),
  objective_detail: z.string().nullable(),
  target_value: z.object({ value: z.number(), unit: z.string() }).nullable(),
  preserve: z.array(z.string()),
  budget: z.object({
    variants: z.number().int().nullable(),
    amount: z.number().nullable(),
    currency: z.string().nullable(),
  }),
  expression_host: z.string().nullable(),
  assay: z.string().nullable(),
  /** Clauses the parser could not place, shown rather than dropped. */
  unparsed: z.array(z.string()),
  method: z.string().optional(),
  note: z.string().optional(),
  restatement: z.string().optional(),
  matched_phrases: z.array(z.string()).optional(),
})

export type GoalSpec = z.infer<typeof goalSpecSchema>

export const goalSchema = z.object({
  id: z.string().uuid(),
  project_id: z.string().uuid(),
  target_id: z.string().uuid(),
  raw_text: z.string(),
  spec: goalSpecSchema,
  restatement: z.string(),
  method: z.string(),
  note: z.string(),
  missing_required: z.array(z.string()),
  is_confirmed: z.boolean(),
  confirmed_at: z.string().datetime({ offset: true }).nullable(),
  expectations: z.object({
    will: z.array(z.string()),
    will_not: z.array(z.string()),
  }),
})

export type Goal = z.infer<typeof goalSchema>
export const goalListSchema = z.array(goalSchema)

export const preflightSchema = z.object({
  can_start: z.boolean(),
  reason: z.string().nullable(),
  remedy: z.string().nullable(),
})

export type Preflight = z.infer<typeof preflightSchema>

/* ------------------------------------------------------------ constraints */

export const constraintKindSchema = z.enum([
  'catalytic',
  'ligand_contact',
  'cofactor_contact',
  'binding_interface',
  'disulfide',
  'signal_peptide',
  'purification_tag',
  'do_not_touch',
])

export type ConstraintKind = z.infer<typeof constraintKindSchema>

export const constraintSchema = z.object({
  id: z.string().uuid(),
  kind: constraintKindSchema,
  positions: z.array(z.number().int()),
  /** The same positions as the canonical scheme labels them. */
  labels: z.array(z.string()),
  note: z.string().nullable(),
})

export type Constraint = z.infer<typeof constraintSchema>
export const constraintListSchema = z.array(constraintSchema)

/** A proposal read from UniProt. Constrains nothing until accepted. */
export const suggestionSchema = z.object({
  kind: constraintKindSchema,
  positions: z.array(z.number().int()),
  labels: z.array(z.string()),
  residues: z.array(z.string()),
  source: z.string(),
  note: z.string(),
})

export type Suggestion = z.infer<typeof suggestionSchema>
export const suggestionListSchema = z.array(suggestionSchema)

/* -------------------------------------------------------------------- runs */

export const runStatusSchema = z.enum([
  'pending',
  'running',
  'succeeded',
  'failed',
  'cancelled',
])

export type RunStatus = z.infer<typeof runStatusSchema>

export const stageStatusSchema = z.enum([
  'pending',
  'running',
  'succeeded',
  'failed',
  'skipped',
  'cancelled',
])

export type StageStatus = z.infer<typeof stageStatusSchema>

/**
 * The model version a stage used, exactly as the provenance trail records it.
 * `is_mock` is what badges every number the stage produced — nothing in the web
 * app decides that by looking at the model's name.
 */
export const modelVersionSchema = z.object({
  id: z.string().uuid(),
  model_id: z.string(),
  name: z.string(),
  version: z.string(),
  weights_hash: z.string(),
  modality: z.string(),
  citation: z.string(),
  is_mock: z.boolean(),
})

export type ModelVersion = z.infer<typeof modelVersionSchema>

export const runStageSchema = z.object({
  id: z.string().uuid(),
  ordinal: z.number().int(),
  name: z.string(),
  status: stageStatusSchema,
  runtime_ms: z.number().int().nullable(),
  input_hash: z.string().nullable(),
  logs: z.string().nullable(),
  error: z.string().nullable(),
  model: modelVersionSchema.nullable(),
})

export type RunStage = z.infer<typeof runStageSchema>

export const runSchema = z.object({
  id: z.string().uuid(),
  project_id: z.string().uuid(),
  target_id: z.string().uuid(),
  goal_id: z.string().uuid(),
  status: runStatusSchema,
  config: z.object({
    predictors: z.array(z.string()).optional(),
    max_variants: z.number().int().nullable().optional(),
    override_constraints: z.boolean().optional(),
  }),
  input_hash: z.string(),
  parent_run_id: z.string().uuid().nullable(),
  created_at: z.string().datetime({ offset: true }),
  started_at: z.string().datetime({ offset: true }).nullable(),
  finished_at: z.string().datetime({ offset: true }).nullable(),
  error: z.string().nullable(),
  /** True when any model version in this run fabricates its numbers. */
  is_demo: z.boolean(),
  /** Terminal runs stop the client polling. Decided by the API, not here. */
  is_terminal: z.boolean(),
  stages: z.array(runStageSchema),
})

export type Run = z.infer<typeof runSchema>
export const runListSchema = z.array(runSchema)

/** One number, with the model version that produced it and whether it is real. */
export const scoreCellSchema = z.object({
  metric: z.string(),
  value: z.number(),
  uncertainty: z.number().nullable(),
  ci_low: z.number().nullable(),
  ci_high: z.number().nullable(),
  model_version_id: z.string().uuid(),
  model_id: z.string(),
  is_mock: z.boolean(),
})

export type ScoreCell = z.infer<typeof scoreCellSchema>

export const metricSchema = z.object({
  id: z.string(),
  label: z.string(),
  unit: z.string().nullable(),
  sign_convention: z.string(),
  higher_is_better: z.boolean(),
  reports_interval: z.boolean(),
})

export type Metric = z.infer<typeof metricSchema>

/**
 * Geometry for one residue. Every field may be null, and null means the
 * calculation did not produce it — never zero, never a default.
 */
export const residueFeaturesSchema = z.object({
  /**
   * How the structure file numbers this residue. The viewer addresses residues
   * in author numbering; the table shows the canonical scheme. They are
   * different numbers and are never converted by arithmetic.
   */
  author_label: z.string().nullable().default(null),
  /** Absolute solvent accessible surface area, square angstroms. */
  asa: z.number().nullable().default(null),
  /** ASA over the published maximum for this residue type (Tien 2013). */
  rsa: z.number().nullable().default(null),
  region: z.enum(['core', 'boundary', 'surface']).nullable().default(null),
  /**
   * Exposed in the protein alone, buried once cofactors are present. The
   * reported RSA is the apo value; this says the apo value is misleading here.
   */
  buried_by_ligand: z.boolean().default(false),
  rsa_with_ligands: z.number().nullable().default(null),
  /** Minimum non-hydrogen atom distance to the user-annotated active site. */
  distance_to_active_site: z.number().nullable().default(null),
})

export type ResidueFeatures = z.infer<typeof residueFeaturesSchema>

export const rankedVariantSchema = z.object({
  rank: z.number().int(),
  /** Written in the canonical numbering scheme, never in sequence index. */
  code: z.string(),
  hgvs: z.string(),
  label: z.string(),
  sequence_position: z.number().int().nullable(),
  features: residueFeaturesSchema,
  /** Mean of the predictors' normalised ranks. Not a physical quantity. */
  consensus: z.number(),
  /** Null when only one predictor scored it — zero would read as unanimity. */
  disagreement: z.number().nullable(),
  sources_scored: z.number().int(),
  cells: z.array(scoreCellSchema),
  /** The constraint kinds that removed this variant. Empty for survivors. */
  filtered_by: z.array(z.string()).default([]),
})

export type RankedVariant = z.infer<typeof rankedVariantSchema>

export const rankingSchema = z.object({
  run_id: z.string().uuid(),
  scheme_label: z.string(),
  metrics: z.array(metricSchema),
  /** Metric id to the reason it has no values. The cell reads as an em dash. */
  unavailable: z.record(z.string(), z.string()),
  total_scored: z.number().int(),
  total_filtered: z.number().int(),
  total_ranked: z.number().int(),
  budget: z.number().int().nullable(),
  is_demo: z.boolean(),
  rows: z.array(rankedVariantSchema),
  /**
   * Every parameter that produced the geometry columns: reference table and
   * DOI, radii set, probe radius, cutoffs in force, coordinate set, ligand
   * handling. Empty when nothing was measured — `features_note` says why.
   */
  features_manifest: z.record(z.string(), z.unknown()).default({}),
  features_note: z.string().nullable().default(null),
})

export type Ranking = z.infer<typeof rankingSchema>

/** Variants a constraint removed, each with the constraint that removed it. */
export const filteredSchema = z.object({
  run_id: z.string().uuid(),
  override: z.boolean(),
  kept: z.number().int(),
  removed: z.record(z.string(), z.array(z.string())),
  constrained_positions: z.record(z.string(), z.array(z.string())),
})

export type Filtered = z.infer<typeof filteredSchema>

export const runDiffSchema = z.object({
  run_id: z.string().uuid(),
  parent_run_id: z.string().uuid(),
  config_changes: z.array(
    z.object({ key: z.string(), before: z.unknown(), after: z.unknown() }),
  ),
  stages: z.array(
    z.object({
      name: z.string(),
      status_before: z.string().nullable(),
      status_after: z.string(),
      runtime_ms_before: z.number().int().nullable(),
      runtime_ms_after: z.number().int().nullable(),
      /** Identical input hash, so the stage did not re-execute. */
      reused: z.boolean(),
    }),
  ),
  scores: z.record(z.string(), z.number().int()),
  entered: z.array(z.string()),
  left: z.array(z.string()),
  moved: z.array(
    z.object({ code: z.string(), before: z.number().int(), after: z.number().int() }),
  ),
})

export type RunDiff = z.infer<typeof runDiffSchema>

// --------------------------------------------------------------------------- //
// Design sets — specification §5.7
// --------------------------------------------------------------------------- //

/**
 * Whether two mutated positions are close enough to interact structurally.
 *
 * Three states, not two. `unknown` means the separation could not be measured —
 * no structure, unreconciled numbering, or a residue the coordinates do not
 * resolve — and it must never be rendered the way `beyond` is. A component that
 * treats "not within" as "safely apart" would tell a bench scientist two
 * mutations are independent on the basis of no evidence at all.
 */
export const proximitySchema = z.enum(['within', 'beyond', 'unknown'])

export type Proximity = z.infer<typeof proximitySchema>

export const pairFlagSchema = z.object({
  a_code: z.string(),
  b_code: z.string(),
  a_position: z.number().int(),
  b_position: z.number().int(),
  proximity: proximitySchema,
  /** Minimum non-hydrogen atom separation, angstroms. Null when unknown. */
  separation_angstrom: z.number().nullable(),
  /** Why the separation is unknown. Null unless `proximity` is `unknown`. */
  reason: z.string().nullable(),
})

export type PairFlag = z.infer<typeof pairFlagSchema>

export const additiveSchema = z.object({
  metric: z.string(),
  label: z.string(),
  unit: z.string().nullable(),
  sign_convention: z.string(),
  /** Null whenever any component lacks a value. Never a partial sum. */
  total: z.number().nullable(),
  contributions: z.array(z.object({ code: z.string(), value: z.number() })),
  missing: z.array(z.string()),
  /** The additivity statement. Always present — see `domain/epistasis`. */
  assumption: z.string(),
  interval_note: z.string(),
})

export type Additive = z.infer<typeof additiveSchema>

export const designMemberSchema = z.object({
  variant_id: z.string().uuid(),
  code: z.string(),
  hgvs: z.string(),
  mutations: z.array(z.string()),
  sequence_positions: z.array(z.number().int()),
  is_stacked: z.boolean(),
  included_via_override: z.boolean(),
  override_reason: z.string().nullable(),
  pairs: z.array(pairFlagSchema),
  additive: z.array(additiveSchema),
})

export type DesignMember = z.infer<typeof designMemberSchema>

export const costLineSchema = z.object({
  description: z.string(),
  quantity: z.number().int(),
  length: z.number().int(),
  unit: z.string(),
  amount: z.number().nullable(),
  unpriced_reason: z.string().nullable(),
})

export const costSchema = z.object({
  currency: z.string().nullable(),
  /** Null when anything is unpriced. No price is ever invented. */
  total: z.number().nullable(),
  lines: z.array(costLineSchema),
  unavailable_reason: z.string().nullable(),
  budget_amount: z.number().nullable(),
  budget_currency: z.string().nullable(),
  /** Null, never false, when either side is unknown. */
  over_budget: z.boolean().nullable(),
  remaining: z.number().nullable(),
})

export type Cost = z.infer<typeof costSchema>

/**
 * The epistasis warning as data. Specification §5.7 requires it to be
 * unmissable, so it arrives with the set rather than being assembled by a
 * component that could forget it.
 */
export const epistasisWarningSchema = z.object({
  stacked_designs: z.number().int(),
  assumption: z.string(),
  cutoff_angstrom: z.number(),
  distance_convention: z.string(),
  pairs_total: z.number().int(),
  pairs_within_cutoff: z.number().int(),
  /** Counted separately so "no structure" cannot read as "nothing is close". */
  pairs_unknown: z.number().int(),
})

export type EpistasisWarning = z.infer<typeof epistasisWarningSchema>

export const designSetSchema = z.object({
  design_set_id: z.string().uuid(),
  project_id: z.string().uuid(),
  run_id: z.string().uuid(),
  name: z.string(),
  note: z.string().nullable(),
  scheme_label: z.string(),
  members: z.array(designMemberSchema),
  warning: epistasisWarningSchema,
  cost: costSchema,
  geometry_manifest: z.record(z.string(), z.unknown()).default({}),
  geometry_note: z.string().nullable().default(null),
  is_demo: z.boolean(),
})

export type DesignSet = z.infer<typeof designSetSchema>

export const designSetSummarySchema = z.object({
  design_set_id: z.string().uuid(),
  project_id: z.string().uuid(),
  run_id: z.string().uuid(),
  name: z.string(),
  note: z.string().nullable(),
  budget_amount: z.number().nullable(),
  budget_currency: z.string().nullable(),
})

export type DesignSetSummary = z.infer<typeof designSetSummarySchema>

export const designSetListSchema = z.array(designSetSummarySchema)

export const stackResultSchema = z.object({
  design_set_id: z.string().uuid(),
  /** What was left out and why. Never empty when anything was skipped. */
  notes: z.array(z.string()),
})

export type StackResult = z.infer<typeof stackResultSchema>

/* -------------------------------------------------------------------------- */
/* Phase 8 — results intake and the scorecard                                  */
/* -------------------------------------------------------------------------- */

export const columnMappingSchema = z.object({
  label: z.string(),
  value: z.string(),
  sd: z.string().nullable().default(null),
  replicate: z.string().nullable().default(null),
})

export type ColumnMapping = z.infer<typeof columnMappingSchema>

export const inspectSchema = z.object({
  headers: z.array(z.string()),
  /** `,` or a tab. Shown because a file split on the wrong character produces
   * one enormous column, which is otherwise puzzling rather than obvious. */
  delimiter: z.string(),
  row_count: z.number().int(),
  columns: z.array(z.object({ name: z.string(), sample: z.array(z.string()) })),
  /** Null when nothing in the headers looked like a mutation code and a value.
   * Never a blind guess at the first two columns. */
  suggested: columnMappingSchema.nullable(),
})

export type Inspect = z.infer<typeof inspectSchema>

export const previewRowSchema = z.object({
  index: z.number().int(),
  raw_label: z.string(),
  value: z.number(),
  sd: z.number().nullable(),
  replicate: z.number().int().nullable(),
  outcome: z.string(),
  code: z.string().nullable(),
  hgvs: z.string().nullable(),
  detail: z.string(),
})

export type PreviewRow = z.infer<typeof previewRowSchema>

const shiftedRowSchema = z.object({
  index: z.number().int(),
  raw_label: z.string(),
  code: z.string(),
})

/**
 * A numbering shift the product found but has not applied. Offered for the user
 * to accept or reject; `explained_without_variant` is present so the proposal
 * cannot overstate what accepting it repairs.
 */
export const offsetProposalSchema = z.object({
  offset: z.number().int(),
  witnesses: z.number().int(),
  would_join: z.array(shiftedRowSchema),
  explained_without_variant: z.array(shiftedRowSchema),
})

export type OffsetProposal = z.infer<typeof offsetProposalSchema>

export const measurementPreviewSchema = z.object({
  scheme_label: z.string(),
  delimiter: z.string(),
  headers: z.array(z.string()),
  rows: z.array(previewRowSchema),
  total_rows: z.number().int(),
  joined: z.number().int(),
  unjoined: z.number().int(),
  problems: z.array(z.object({ index: z.number().int(), detail: z.string() })),
  outcome_counts: z.record(z.string(), z.number()),
  offset: offsetProposalSchema.nullable(),
  /** Never blank alongside a null `offset`: "we found nothing" and "we did not
   * look" are different answers and the interface shows which one happened. */
  offset_note: z.string(),
  stale_variants: z.number().int(),
})

export type MeasurementPreview = z.infer<typeof measurementPreviewSchema>

export const importResultSchema = z.object({
  experiment_id: z.string().uuid(),
  written: z.number().int(),
  joined: z.number().int(),
  unjoined: z.number().int(),
  problems: z.array(z.object({ index: z.number().int(), detail: z.string() })),
})

export type ImportResult = z.infer<typeof importResultSchema>

export const experimentSchema = z.object({
  id: z.string().uuid(),
  assay: z.string(),
  metric: z.string(),
  unit: z.string(),
  /** Null when the import never stated which way the assay points. The
   * scorecard then reports that it cannot rank, rather than guessing. */
  higher_is_better: z.boolean().nullable(),
  source_note: z.string().nullable(),
  protocol: z.string().nullable(),
  operator: z.string().nullable(),
  performed_on: z.string().nullable(),
  total: z.number().int(),
  joined: z.number().int(),
  unjoined: z.number().int(),
})

export type Experiment = z.infer<typeof experimentSchema>

export const experimentListSchema = z.array(experimentSchema)

export const scatterPointSchema = z.object({
  /** Identity. `code` is not unique on a card pooled across targets. */
  variant_id: z.string().uuid(),
  code: z.string(),
  hgvs: z.string(),
  predicted: z.number(),
  measured: z.number(),
  /** How many measured rows were averaged into this point. */
  replicates: z.number().int(),
})

export type ScatterPoint = z.infer<typeof scatterPointSchema>

/**
 * One predictor's record against one set of measurements.
 *
 * ARCHITECTURE.md §13: a rank statistic never stands alone. `mae` and
 * `mean_signed_error` are always present as fields, and whenever they are null
 * `error_unavailable_reason` is non-empty — so there is no shape of this object
 * in which a client holds a Spearman coefficient and nothing telling it whether
 * the absolute error was knowable.
 */
export const scorecardSchema = z.object({
  model_id: z.string(),
  model_name: z.string(),
  model_version: z.string(),
  weights_hash: z.string(),
  model_version_id: z.string().uuid(),
  is_mock: z.boolean(),
  predicted_metric: z.string(),
  predicted_unit: z.string(),
  predicted_sign: z.string(),
  measured_metric: z.string(),
  measured_unit: z.string(),
  measured_sign: z.string(),
  n: z.number().int(),
  /** Oriented so +1 means the predictor and the bench agree about quality. */
  spearman: z.number().nullable(),
  precision_k: z.number().int(),
  precision: z.number().nullable(),
  precision_note: z.string(),
  mae: z.number().nullable(),
  mean_signed_error: z.number().nullable(),
  error_unit: z.string().nullable(),
  bias_note: z.string(),
  error_unavailable_reason: z.string(),
  calibration: z.array(
    z.object({ predicted: z.number(), measured: z.number(), count: z.number() }),
  ),
  points: z.array(scatterPointSchema),
  targets: z.array(z.string()),
  /** Distinct target rows behind this card; exceeds `targets.length` when
   * several targets share a name. */
  target_count: z.number().int(),
})

export type Scorecard = z.infer<typeof scorecardSchema>

export const scorecardReportSchema = z.object({
  cards: z.array(scorecardSchema),
  /** Why there is nothing to show, when there is nothing. Never an empty screen
   * with no explanation. */
  note: z.string(),
  measured_variants: z.number().int(),
  unjoined_measurements: z.number().int(),
  metrics: z.array(z.string()),
  is_demo: z.boolean(),
})

export type ScorecardReport = z.infer<typeof scorecardReportSchema>
