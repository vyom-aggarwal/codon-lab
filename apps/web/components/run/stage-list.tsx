import type { RunStage, StageStatus } from '@codonlab/schema'

import { Badge, StatusDot, type BadgeTone } from '@/components/ui/badge'

/**
 * The pipeline, as specification §5.5 states it: a vertical list of stages, each
 * showing model name, version, runtime, input hash and status, with streaming
 * logs behind a disclosure.
 *
 * A stage that did not run says why in its log rather than disappearing. A
 * skipped stage is the reason a column reads as unavailable further down the
 * page, so hiding it would remove the explanation for an absence.
 */

const TONE: Record<StageStatus, BadgeTone> = {
  pending: 'neutral',
  running: 'accent',
  succeeded: 'positive',
  // Amber, not grey: a skipped stage means something is missing from the result.
  skipped: 'warn',
  failed: 'negative',
  cancelled: 'neutral',
}

function runtime(ms: number | null): string {
  if (ms === null) return '—'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

export function StageList({ stages }: { stages: RunStage[] }) {
  return (
    <ol className="border-border rounded-panel divide-border divide-y border">
      {stages.map((stage) => (
        <li key={stage.id} className="p-3">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="flex items-center gap-2">
              <StatusDot tone={TONE[stage.status]} />
              <span className="text-13 text-text font-medium">{stage.name}</span>
            </span>
            <Badge tone={TONE[stage.status]}>{stage.status}</Badge>

            {stage.model ? (
              <>
                <span className="text-12 text-text-muted">
                  {stage.model.name} {stage.model.version}
                </span>
                {/* Weights hash, on screen rather than in a log file: it is what
                    makes a number reproducible months later. */}
                <span className="text-11 text-text-faint font-mono" title={stage.model.weights_hash}>
                  weights {stage.model.weights_hash.replace(/^sha256:/, '').slice(0, 12)}
                </span>
                {stage.model.is_mock ? <Badge tone="warn">Synthetic</Badge> : null}
              </>
            ) : null}

            <span className="text-12 text-text-muted ml-auto tabular-nums">
              {runtime(stage.runtime_ms)}
            </span>
          </div>

          {stage.input_hash ? (
            <p
              className="text-11 text-text-faint mt-1 font-mono"
              title={`Content address of this stage's inputs: ${stage.input_hash}`}
            >
              input {stage.input_hash.replace(/^sha256:/, '').slice(0, 16)}
            </p>
          ) : null}

          {stage.error ? (
            <p className="text-12 text-negative mt-1">{stage.error}</p>
          ) : null}

          {stage.logs ? (
            <details className="mt-2">
              <summary className="text-12 text-accent cursor-pointer select-none">Logs</summary>
              <pre className="bg-surface-sunk text-12 text-text-muted rounded-control mt-1 overflow-x-auto p-2 whitespace-pre-wrap">
                {stage.logs}
              </pre>
            </details>
          ) : null}
        </li>
      ))}
    </ol>
  )
}
