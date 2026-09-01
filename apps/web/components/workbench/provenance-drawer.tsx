'use client'

import type { RankedVariant, Run, ScoreCell } from '@codonlab/schema'
import { X } from 'lucide-react'
import type { Route } from 'next'
import Link from 'next/link'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

/**
 * Where a number came from. The second of the two clicks the Phase 5 gate names:
 * click a row, click the number, and this is open on the model version that
 * produced it.
 *
 * Specification §2.2 asks for model, version, weights hash, inputs, run and
 * time. All six are here, read from the stored `ModelVersion` and `RunStage`
 * rows rather than reconstructed — a provenance record assembled on the client
 * would be a claim about the past rather than a record of it.
 */
export function ProvenanceDrawer({
  cell,
  variant,
  run,
  featuresManifest,
  onClose,
}: {
  cell: ScoreCell | null
  variant: RankedVariant
  run: Run
  featuresManifest: Record<string, unknown>
  onClose: () => void
}) {
  const stage = cell
    ? run.stages.find((candidate) => candidate.model?.id === cell.model_version_id)
    : undefined
  const model = stage?.model ?? null

  return (
    <div className="bg-surface border-border flex h-full flex-col border-l">
      <header className="border-border flex items-center justify-between gap-2 border-b p-3">
        <div className="flex items-center gap-2">
          <h2 className="text-15 font-strong">Provenance</h2>
          <span className="text-12 font-mono">{variant.code}</span>
        </div>
        <Button size="sm" variant="ghost" onClick={onClose} aria-label="Close provenance">
          <X strokeWidth={1.5} />
        </Button>
      </header>

      <div className="divide-border flex-1 divide-y overflow-y-auto">
        {cell && model ? (
          <>
            <Field label="The number">
              <p className="text-13 tabular-nums">
                {cell.metric} = {cell.value.toFixed(4)}
                {cell.uncertainty !== null ? ` ± ${cell.uncertainty.toFixed(4)}` : ''}
              </p>
              {cell.ci_low !== null && cell.ci_high !== null ? (
                <p className="text-12 text-text-muted tabular-nums">
                  95% interval {cell.ci_low.toFixed(4)} to {cell.ci_high.toFixed(4)}
                </p>
              ) : (
                <p className="text-12 text-text-muted">
                  Reported as a point estimate. No interval was invented for it.
                </p>
              )}
              {model.is_mock ? (
                <Badge tone="warn" className="mt-1">
                  Synthetic — not model output
                </Badge>
              ) : null}
            </Field>

            <Field label="Model">
              <p className="text-13">{model.name}</p>
              <dl className="text-12 mt-1 space-y-0.5">
                <Row term="id" value={model.model_id} mono />
                <Row term="version" value={model.version} mono />
                <Row term="weights" value={model.weights_hash} mono />
                <Row term="modality" value={model.modality} />
              </dl>
              <p className="text-12 text-text-muted mt-1">{model.citation}</p>
            </Field>

            <Field label="Stage">
              <p className="text-13">{stage?.name}</p>
              <dl className="text-12 mt-1 space-y-0.5">
                <Row term="status" value={stage?.status ?? '—'} />
                <Row
                  term="runtime"
                  value={stage?.runtime_ms === null ? '—' : `${stage?.runtime_ms} ms`}
                />
                <Row term="input hash" value={stage?.input_hash ?? '—'} mono />
              </dl>
            </Field>
          </>
        ) : (
          <Field label="The number">
            <p className="text-13 text-text-muted">
              Select a score in the inspector to trace it to the model version that
              produced it.
            </p>
          </Field>
        )}

        <Field label="Run">
          <dl className="text-12 space-y-0.5">
            <Row term="run" value={run.id} mono />
            <Row term="inputs" value={run.input_hash} mono />
            <Row term="status" value={run.status} />
            <Row term="started" value={run.started_at ?? '—'} />
            <Row term="finished" value={run.finished_at ?? '—'} />
          </dl>
          <Link
            href={`/runs/${run.id}` as Route}
            className="text-12 text-accent mt-2 inline-block underline-offset-2 hover:underline"
          >
            Open the run and its stage logs
          </Link>
        </Field>

        {Object.keys(featuresManifest).length > 0 ? (
          <Field label="Geometry">
            <p className="text-12 text-text-muted mb-1">
              RSA, burial class and active-site distance are computed, not modelled. Every
              parameter that produced them:
            </p>
            <dl className="text-12 space-y-0.5">
              {flatten(featuresManifest).map(([term, value]) => (
                <Row key={term} term={term} value={value} />
              ))}
            </dl>
          </Field>
        ) : null}
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1 p-3">
      <p className="text-11 text-text-muted font-medium uppercase tracking-wide">{label}</p>
      {children}
    </section>
  )
}

function Row({ term, value, mono }: { term: string; value: string; mono?: boolean }) {
  return (
    <div className="flex gap-2">
      <dt className="text-text-muted w-24 shrink-0">{term}</dt>
      <dd className={mono ? 'min-w-0 break-all font-mono' : 'min-w-0 break-words'}>{value}</dd>
    </div>
  )
}

/** The manifest is nested; the drawer shows it as flat term/value pairs. */
function flatten(value: unknown, prefix = ''): [string, string][] {
  if (value === null || value === undefined) return [[prefix, '—']]
  if (Array.isArray(value)) {
    return [[prefix, value.length === 0 ? 'none' : value.join(', ')]]
  }
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).flatMap(([key, item]) =>
      flatten(item, prefix ? `${prefix}.${key}` : key),
    )
  }
  return [[prefix, String(value)]]
}
