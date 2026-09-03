import {
  constraintListSchema,
  constraintSchema,
  designSetListSchema,
  designSetSchema,
  designSetSummarySchema,
  experimentListSchema,
  filteredSchema,
  importResultSchema,
  inspectSchema,
  measurementPreviewSchema,
  goalListSchema,
  goalSchema,
  metaSchema,
  preflightSchema,
  projectDetailSchema,
  projectListSchema,
  rankingSchema,
  reconciliationSchema,
  runDiffSchema,
  runListSchema,
  runSchema,
  scorecardReportSchema,
  stackResultSchema,
  sequenceTrackSchema,
  suggestionListSchema,
  targetSchema,
  type Constraint,
  type ConstraintKind,
  type DesignSet,
  type ColumnMapping,
  type DesignSetSummary,
  type Experiment,
  type Filtered,
  type ImportResult,
  type Inspect,
  type MeasurementPreview,
  type Goal,
  type GoalSpec,
  type Meta,
  type Preflight,
  type ProjectDetail,
  type ProjectRow,
  type Ranking,
  type Reconciliation,
  type Run,
  type RunDiff,
  type Scorecard,
  type ScorecardReport,
  type SequenceTrack,
  type StackResult,
  type Suggestion,
  type Target,
} from '@codonlab/schema'

import { authHeader } from '@/lib/auth'

/**
 * Structural, so the web app depends on @codonlab/schema and not on zod itself.
 * The validation library is an implementation detail of the schema package.
 */
interface Parser<T> {
  safeParse(input: unknown): { success: true; data: T } | { success: false }
}

/**
 * Server components run inside the container, where the API is reachable by
 * service name; the browser reaches it on localhost. Both are needed.
 */
function baseUrl(): string {
  if (typeof window === 'undefined') {
    return (
      process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
    )
  }
  return process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
}

/** A failure the interface can explain: what broke, and what fixes it. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly remedy: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, schema: Parser<T>): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${baseUrl()}${path}`, {
      cache: 'no-store',
      headers: await authHeader(),
    })
  } catch {
    throw new ApiError(
      'Cannot reach the API.',
      'Start the stack with `docker compose up`, then reload.',
    )
  }

  if (!response.ok) {
    throw new ApiError(
      `The API returned ${response.status} for ${path}.`,
      'Check the api service logs with `docker compose logs api`.',
    )
  }

  const parsed = schema.safeParse(await response.json())
  if (!parsed.success) {
    // Silently coercing a mismatched payload is how a wrong number reaches a
    // scientist. Fail loudly instead.
    throw new ApiError(
      `The API response for ${path} did not match the expected schema.`,
      'The web and api versions are out of step — rebuild with `docker compose up --build`.',
    )
  }
  return parsed.data
}

/**
 * The API reports failures as `{message, remedy}`. That shape is preserved all
 * the way to the screen: an error that does not say what fixes it is useless to
 * someone who is busy.
 */
async function send<T>(path: string, body: unknown, schema: Parser<T>): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${baseUrl()}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(await authHeader()) },
      body: JSON.stringify(body),
      cache: 'no-store',
    })
  } catch {
    throw new ApiError(
      'Cannot reach the API.',
      'Start the stack with `docker compose up`, then retry.',
    )
  }

  if (!response.ok) {
    const detail = await response
      .json()
      .then((payload: unknown) => {
        const shape = payload as { detail?: { message?: string; remedy?: string } }
        return shape.detail
      })
      .catch(() => undefined)

    throw new ApiError(
      detail?.message ?? `The API returned ${response.status}.`,
      detail?.remedy ?? 'Check the input and try again.',
    )
  }

  const parsed = schema.safeParse(await response.json())
  if (!parsed.success) {
    throw new ApiError(
      `The API response for ${path} did not match the expected schema.`,
      'The web and api versions are out of step — rebuild with `docker compose up --build`.',
    )
  }
  return parsed.data
}

export function fetchMeta(): Promise<Meta> {
  return request('/meta', metaSchema)
}

export function fetchProjects(): Promise<ProjectRow[]> {
  return request('/projects', projectListSchema)
}

export function fetchProject(id: string): Promise<ProjectDetail> {
  return request(`/projects/${id}`, projectDetailSchema)
}

export function fetchTarget(id: string): Promise<Target> {
  return request(`/targets/${id}`, targetSchema)
}

/** Per-residue labels for every scheme, for the sequence track. */
export function fetchTrack(id: string): Promise<SequenceTrack> {
  return request(`/targets/${id}/track`, sequenceTrackSchema)
}

export function createProject(body: {
  name: string
  organism?: string
  objective?: string
}): Promise<ProjectDetail> {
  return send('/projects', body, projectDetailSchema)
}

export function createTarget(
  projectId: string,
  body:
    | { source: 'uniprot'; accession: string }
    | { source: 'sequence'; name: string; text: string; organism?: string },
): Promise<Target> {
  return send(`/projects/${projectId}/targets`, body, targetSchema)
}

export function attachStructure(
  targetId: string,
  body: { source: 'pdb' | 'alphafold_db' | 'uploaded_pdb'; identifier?: string; text?: string },
): Promise<Target> {
  return send(`/targets/${targetId}/structures`, body, targetSchema)
}

/** Computes a mapping and returns it. Persists nothing. */
export function previewReconciliation(
  targetId: string,
  body: { structure_id: string; chain_id?: string; use_alignment?: boolean },
): Promise<Reconciliation> {
  return send(`/targets/${targetId}/reconcile`, body, reconciliationSchema)
}

export function acceptReconciliation(
  targetId: string,
  body: { structure_id: string; chain_id?: string; use_alignment?: boolean },
): Promise<Target> {
  return send(`/targets/${targetId}/reconcile/accept`, body, targetSchema)
}

export function confirmCanonical(targetId: string, schemeId: string): Promise<Target> {
  return send(`/targets/${targetId}/numbering/confirm`, { scheme_id: schemeId }, targetSchema)
}

/* ------------------------------------------------------------------ goals */

export function fetchGoals(targetId: string): Promise<Goal[]> {
  return request(`/targets/${targetId}/goals`, goalListSchema)
}

export function fetchGoal(goalId: string): Promise<Goal> {
  return request(`/goals/${goalId}`, goalSchema)
}

export function createGoal(targetId: string, text: string): Promise<Goal> {
  return send(`/targets/${targetId}/goals`, { text }, goalSchema)
}

/** Replace the parse with the user's edited chips. Clears any confirmation. */
export function updateGoal(goalId: string, spec: GoalSpec): Promise<Goal> {
  return send(`/goals/${goalId}`, { spec }, goalSchema)
}

export function confirmGoal(goalId: string): Promise<Goal> {
  return send(`/goals/${goalId}/confirm`, {}, goalSchema)
}

/** Asks the API the same question the run pipeline will ask. */
export function fetchPreflight(goalId: string): Promise<Preflight> {
  return request(`/goals/${goalId}/preflight`, preflightSchema)
}

/* ------------------------------------------------------------ constraints */

export function fetchConstraints(targetId: string): Promise<Constraint[]> {
  return request(`/targets/${targetId}/constraints`, constraintListSchema)
}

export function fetchSuggestions(targetId: string): Promise<Suggestion[]> {
  return request(`/targets/${targetId}/constraints/suggestions`, suggestionListSchema)
}

export function addConstraint(
  targetId: string,
  body: { kind: ConstraintKind; positions: number[]; note?: string },
): Promise<Constraint> {
  return send(`/targets/${targetId}/constraints`, body, constraintSchema)
}

/* ------------------------------------------------------------------- runs */

/** Start a design run. The API refuses unless the objective is confirmed. */
export function startRun(
  goalId: string,
  body: { predictors?: string[]; max_variants?: number; override_constraints?: boolean } = {},
): Promise<Run> {
  return send(`/goals/${goalId}/runs`, body, runSchema)
}

export function fetchRun(runId: string): Promise<Run> {
  return request(`/runs/${runId}`, runSchema)
}

export function fetchRuns(targetId: string): Promise<Run[]> {
  return request(`/targets/${targetId}/runs`, runListSchema)
}

export function cancelRun(runId: string): Promise<Run> {
  return send(`/runs/${runId}/cancel`, {}, runSchema)
}

/** Re-run with one parameter changed. The child records its parent, for the diff. */
export function rerun(
  runId: string,
  body: { predictors?: string[]; max_variants?: number; override_constraints?: boolean },
): Promise<Run> {
  return send(`/runs/${runId}/rerun`, body, runSchema)
}

/**
 * Omitting `limit` applies the run's own budget, which is usually a handful of
 * rows. Pass a limit to get the whole ranking.
 */
export function fetchRanking(
  runId: string,
  limit?: number,
  options: { includeFiltered?: boolean } = {},
): Promise<Ranking> {
  const query = new URLSearchParams()
  if (limit !== undefined) query.set('limit', String(limit))
  if (options.includeFiltered) query.set('include_filtered', 'true')
  const suffix = query.size > 0 ? `?${query.toString()}` : ''
  return request(`/runs/${runId}/ranking${suffix}`, rankingSchema)
}

/** Variants a constraint removed, each with the constraint that removed it. */
export function fetchFiltered(runId: string): Promise<Filtered> {
  return request(`/runs/${runId}/filtered`, filteredSchema)
}

export function fetchDiff(runId: string): Promise<RunDiff> {
  return request(`/runs/${runId}/diff`, runDiffSchema)
}

/* ------------------------------------------------------------ constraints */

export async function deleteConstraint(constraintId: string): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${baseUrl()}/constraints/${constraintId}`, {
      method: 'DELETE',
      cache: 'no-store',
      headers: await authHeader(),
    })
  } catch {
    throw new ApiError('Cannot reach the API.', 'Start the stack with `docker compose up`.')
  }
  if (!response.ok) {
    throw new ApiError(
      `The API returned ${response.status} removing that constraint.`,
      'Reload the page and try again.',
    )
  }
}

/* ------------------------------------------------------------ design sets */

export function fetchDesignSets(runId: string): Promise<DesignSetSummary[]> {
  return request(`/runs/${runId}/design-sets`, designSetListSchema)
}

export function fetchDesignSet(designSetId: string): Promise<DesignSet> {
  return request(`/design-sets/${designSetId}`, designSetSchema)
}

export function createDesignSet(
  runId: string,
  body: {
    name: string
    note?: string
    budget_amount?: number | null
    budget_currency?: string | null
  },
): Promise<DesignSetSummary> {
  return send(`/runs/${runId}/design-sets`, body, designSetSummarySchema)
}

/**
 * Adds designs to a set. The API refuses a constrained position unless
 * `override` is true *and* a reason is given, and records every override —
 * specification §7. The refusal is deliberately not pre-empted here: a check
 * that lives only on a screen is a check the API does not have.
 */
export function addDesignMembers(
  designSetId: string,
  body: { codes: string[]; override?: boolean; override_reason?: string },
): Promise<DesignSet> {
  return send(`/design-sets/${designSetId}/members`, body, designSetSchema)
}

export function stackDesigns(
  designSetId: string,
  body: { codes: string[]; size: number; limit?: number },
): Promise<StackResult> {
  return send(`/design-sets/${designSetId}/stack`, body, stackResultSchema)
}

export async function removeDesignMember(
  designSetId: string,
  variantId: string,
): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${baseUrl()}/design-sets/${designSetId}/members/${variantId}`, {
      method: 'DELETE',
      cache: 'no-store',
      headers: await authHeader(),
    })
  } catch {
    throw new ApiError('Cannot reach the API.', 'Start the stack with `docker compose up`.')
  }
  if (!response.ok) {
    throw new ApiError(
      `The API returned ${response.status} removing that design.`,
      'Reload the page and try again.',
    )
  }
}

/* -------------------------------------------------------------------------- */
/* Phase 8 — results intake and the scorecard                                  */
/* -------------------------------------------------------------------------- */

/** Read a pasted or uploaded table's headers. Writes nothing. */
export function inspectMeasurements(targetId: string, text: string): Promise<Inspect> {
  return send(`/targets/${targetId}/measurements/inspect`, { text }, inspectSchema)
}

/**
 * What an import would do, without doing it.
 *
 * `offset` is null until the user accepts a proposed numbering shift. Nothing
 * applies one on their behalf — the proposal is returned, shown, and accepted
 * or rejected explicitly.
 */
export function previewMeasurements(
  targetId: string,
  body: { text: string; mapping: ColumnMapping; offset: number | null },
): Promise<MeasurementPreview> {
  return send(`/targets/${targetId}/measurements/preview`, body, measurementPreviewSchema)
}

export function importMeasurements(
  targetId: string,
  body: {
    text: string
    mapping: ColumnMapping
    assay: string
    metric: string
    unit: string
    /** Required. Which direction is a better result is a fact about the assay
     * that only the person who ran it knows, so the form has no default. */
    higher_is_better: boolean
    offset: number | null
    source_note: string | null
  },
): Promise<ImportResult> {
  return send(`/targets/${targetId}/measurements`, body, importResultSchema)
}

export function fetchExperiments(projectId: string): Promise<Experiment[]> {
  return request(`/projects/${projectId}/experiments`, experimentListSchema)
}

export function fetchTargetScorecard(targetId: string): Promise<ScorecardReport> {
  return request(`/targets/${targetId}/scorecard`, scorecardReportSchema)
}

/** The persistent scorecard, pooled across every target the lab has measured. */
export function fetchLabScorecard(): Promise<ScorecardReport> {
  return request('/scorecard', scorecardReportSchema)
}

export type { Scorecard }
