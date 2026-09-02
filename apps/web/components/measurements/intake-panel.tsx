'use client'

import { AlertTriangle, Check, Upload } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useState } from 'react'

import type { ColumnMapping, Inspect, MeasurementPreview } from '@codonlab/schema'
import { InlineError } from '@/components/inline-error'
import {
  Badge,
  Button,
  Input,
  Select,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from '@/components/ui'
import {
  ApiError,
  importMeasurements,
  inspectMeasurements,
  previewMeasurements,
} from '@/lib/api'

/**
 * Results intake. Specification §5.9: "upload a CSV of measured values or paste
 * from a plate reader; column-mapping UI with a preview; fuzzy-join to variants
 * by mutation code with manual override."
 *
 * The screen is a confirmation gate, the same shape as the goal composer. Three
 * steps, and nothing is written until the last:
 *
 *  1. **Read** the file — headers only, so the mapping dropdowns can be filled.
 *  2. **Map and preview** — every row is joined *in memory* and shown back with
 *     its outcome. A column mapping is a guess about someone else's
 *     spreadsheet, and guessing wrong files a column of replicate numbers as
 *     measured values.
 *  3. **Import** — writes an experiment and one measurement per row, joined or
 *     not.
 *
 * Two things this component refuses to do on the user's behalf.
 *
 * **It never applies a numbering shift silently.** When the API proposes one it
 * is rendered with its evidence and two buttons. The default is not to apply it.
 *
 * **It has no default for "higher is better".** Which direction is a better
 * result is a fact about the assay that only the person who ran it knows, and
 * every rank statistic on the scorecard needs it. The control starts unset and
 * the import button stays disabled until it is answered.
 */

const ASSAYS = [
  { value: 'thermal_stability', label: 'Thermal stability' },
  { value: 'activity', label: 'Activity' },
  { value: 'expression', label: 'Expression' },
  { value: 'binding', label: 'Binding' },
  { value: 'other', label: 'Other' },
]

type Direction = 'unset' | 'higher' | 'lower'

/** Radix Select cannot carry an empty-string value, so "no column" needs a token. */
const NONE = '__none__'

export function IntakePanel({ targetId }: { targetId: string }) {
  const router = useRouter()

  const [text, setText] = useState('')
  const [inspected, setInspected] = useState<Inspect | null>(null)
  const [mapping, setMapping] = useState<ColumnMapping | null>(null)
  const [preview, setPreview] = useState<MeasurementPreview | null>(null)
  const [offset, setOffset] = useState<number | null>(null)

  const [assay, setAssay] = useState('thermal_stability')
  const [metric, setMetric] = useState('')
  const [unit, setUnit] = useState('')
  const [direction, setDirection] = useState<Direction>('unset')
  const [sourceNote, setSourceNote] = useState('')

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<{ message: string; remedy: string } | null>(null)

  function fail(caught: unknown) {
    if (caught instanceof ApiError) setError({ message: caught.message, remedy: caught.remedy })
    else throw caught
  }

  async function onRead(next: string) {
    setText(next)
    setPreview(null)
    setOffset(null)
    setError(null)
    if (!next.trim()) {
      setInspected(null)
      setMapping(null)
      return
    }
    setBusy(true)
    try {
      const result = await inspectMeasurements(targetId, next)
      setInspected(result)
      setMapping(result.suggested)
    } catch (caught) {
      setInspected(null)
      fail(caught)
    } finally {
      setBusy(false)
    }
  }

  async function onPreview(withOffset: number | null) {
    if (!mapping) return
    setBusy(true)
    setError(null)
    try {
      setPreview(await previewMeasurements(targetId, { text, mapping, offset: withOffset }))
      setOffset(withOffset)
    } catch (caught) {
      fail(caught)
    } finally {
      setBusy(false)
    }
  }

  async function onImport() {
    if (!mapping || direction === 'unset') return
    setBusy(true)
    setError(null)
    try {
      await importMeasurements(targetId, {
        text,
        mapping,
        assay,
        metric,
        unit,
        higher_is_better: direction === 'higher',
        offset,
        source_note: sourceNote.trim() || null,
      })
      router.push(`/targets/${targetId}/scorecard`)
      router.refresh()
    } catch (caught) {
      fail(caught)
    } finally {
      setBusy(false)
    }
  }

  const canImport =
    preview !== null && mapping !== null && direction !== 'unset' && metric.trim() !== ''
      && unit.trim() !== '' && !busy

  return (
    <div className="space-y-6 p-4">
      <header>
        <h1 className="text-18 text-text">Import measured results</h1>
        <p className="text-13 text-text-muted mt-1">
          Paste from a plate reader or drop a CSV. Nothing is written until the preview is
          confirmed.
        </p>
      </header>

      {error ? <InlineError message={error.message} remedy={error.remedy} /> : null}

      {/* ---------------------------------------------------------- step 1 */}
      <section className="space-y-2">
        <h2 className="text-15 text-text">1. The file</h2>
        <label className="text-12 text-text-muted block" htmlFor="measurement-text">
          Comma- or tab-separated, with a header row.
        </label>
        <textarea
          id="measurement-text"
          value={text}
          onChange={(event) => void onRead(event.target.value)}
          rows={6}
          spellCheck={false}
          placeholder={'mutant,T50\nA32N,48.6\nE33K,47.1'}
          className="border-border rounded-control bg-surface text-13 text-text placeholder:text-text-faint focus:border-border-strong focus:ring-accent w-full p-2 font-mono focus:ring-2 focus:outline-none"
        />
        <label className="text-12 text-text-muted inline-flex cursor-pointer items-center gap-1.5">
          <Upload className="size-4" strokeWidth={1.5} />
          <span>Choose a file</span>
          <input
            type="file"
            accept=".csv,.tsv,.txt,text/csv,text/plain"
            className="sr-only"
            onChange={async (event) => {
              const file = event.target.files?.[0]
              if (file) {
                const contents = await file.text()
                setSourceNote(file.name)
                await onRead(contents)
              }
            }}
          />
        </label>

        {inspected ? (
          <p className="text-12 text-text-muted">
            {inspected.row_count.toLocaleString()} rows, {inspected.headers.length} columns, split
            on {inspected.delimiter === '\t' ? 'tab' : 'comma'}.
          </p>
        ) : null}
      </section>

      {/* ---------------------------------------------------------- step 2 */}
      {inspected ? (
        <section className="space-y-3">
          <h2 className="text-15 text-text">2. Which column is which</h2>
          {inspected.suggested === null ? (
            <p className="text-12 text-text-muted">
              No column looked like a mutation code and a value, so nothing is pre-selected.
              Choose them below.
            </p>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <ColumnPicker
              label="Mutation code"
              required
              headers={inspected}
              value={mapping?.label ?? ''}
              onChange={(next) =>
                setMapping((current) => ({
                  label: next,
                  value: current?.value ?? '',
                  sd: current?.sd ?? null,
                  replicate: current?.replicate ?? null,
                }))
              }
            />
            <ColumnPicker
              label="Measured value"
              required
              headers={inspected}
              value={mapping?.value ?? ''}
              onChange={(next) =>
                setMapping((current) => ({
                  label: current?.label ?? '',
                  value: next,
                  sd: current?.sd ?? null,
                  replicate: current?.replicate ?? null,
                }))
              }
            />
            <ColumnPicker
              label="Standard deviation"
              headers={inspected}
              value={mapping?.sd ?? ''}
              allowNone
              onChange={(next) =>
                setMapping((current) =>
                  current ? { ...current, sd: next || null } : current,
                )
              }
            />
            <ColumnPicker
              label="Replicate"
              headers={inspected}
              value={mapping?.replicate ?? ''}
              allowNone
              onChange={(next) =>
                setMapping((current) =>
                  current ? { ...current, replicate: next || null } : current,
                )
              }
            />
          </div>

          <Button
            onClick={() => void onPreview(offset)}
            disabled={!mapping?.label || !mapping?.value || busy}
          >
            Preview the join
          </Button>
        </section>
      ) : null}

      {/* ---------------------------------------------------------- step 3 */}
      {preview ? (
        <section className="space-y-3">
          <h2 className="text-15 text-text">3. What this would do</h2>

          <dl className="text-12 flex flex-wrap gap-x-6 gap-y-1">
            <div className="flex gap-1.5">
              <dt className="text-text-muted">Rows</dt>
              <dd className="text-text tabular-nums">{preview.total_rows.toLocaleString()}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-text-muted">Joined</dt>
              <dd className="text-text tabular-nums">{preview.joined.toLocaleString()}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-text-muted">Unjoined</dt>
              <dd
                className={
                  preview.unjoined > 0 ? 'text-warn tabular-nums' : 'text-text tabular-nums'
                }
              >
                {preview.unjoined.toLocaleString()}
              </dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-text-muted">Numbering</dt>
              <dd className="text-text">{preview.scheme_label}</dd>
            </div>
          </dl>

          <p className="text-12 text-text-muted">
            Every row is written, joined or not. An unjoined row keeps the label the file gave it
            and can be resolved by hand later — nothing is dropped at import.
          </p>

          {preview.stale_variants > 0 ? (
            <p className="text-12 text-text-muted">
              {preview.stale_variants.toLocaleString()} variant rows on this target are written in
              a numbering scheme it no longer treats as canonical. They are excluded from the
              join, so a code cannot attach to a residue this target has since renumbered.
            </p>
          ) : null}

          {preview.offset ? (
            <OffsetProposalPanel
              proposal={preview.offset}
              schemeLabel={preview.scheme_label}
              busy={busy}
              onAccept={() => void onPreview(preview.offset?.offset ?? null)}
            />
          ) : preview.unjoined > 0 ? (
            <p className="text-12 text-text-muted">{preview.offset_note}</p>
          ) : null}

          {preview.problems.length > 0 ? (
            <div className="border-warn/30 bg-warn/8 rounded-panel border p-3">
              <p className="text-12 text-text font-strong">
                {preview.problems.length.toLocaleString()} rows could not be read and will not be
                imported
              </p>
              <ul className="text-12 text-text-muted mt-1 space-y-0.5">
                {preview.problems.slice(0, 5).map((problem) => (
                  <li key={problem.index}>
                    Row {problem.index}: {problem.detail}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <PreviewTable preview={preview} />

          {/* ------------------------------------------------------ step 4 */}
          <h2 className="text-15 text-text pt-2">4. What was measured</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="block">
              <span className="text-12 text-text-muted">Assay</span>
              <Select
                value={assay}
                onValueChange={setAssay}
                options={ASSAYS}
                aria-label="Assay"
              />
            </label>
            <label className="block">
              <span className="text-12 text-text-muted">Metric name</span>
              <Input
                value={metric}
                onChange={(event) => setMetric(event.target.value)}
                placeholder="t50_celsius"
              />
            </label>
            <label className="block">
              <span className="text-12 text-text-muted">Unit</span>
              <Input
                value={unit}
                onChange={(event) => setUnit(event.target.value)}
                placeholder="°C"
              />
            </label>
            <label className="block">
              <span className="text-12 text-text-muted">Source</span>
              <Input
                value={sourceNote}
                onChange={(event) => setSourceNote(event.target.value)}
                placeholder="plate-3.csv, or a DOI"
              />
            </label>
          </div>

          <fieldset className="border-border rounded-panel border p-3">
            <legend className="text-12 text-text-muted px-1">
              Is a higher value a better result?
            </legend>
            <div className="flex flex-wrap items-center gap-4">
              <label className="text-13 text-text flex items-center gap-1.5">
                <input
                  type="radio"
                  name="direction"
                  checked={direction === 'higher'}
                  onChange={() => setDirection('higher')}
                  className="accent-accent"
                />
                Higher is better
              </label>
              <label className="text-13 text-text flex items-center gap-1.5">
                <input
                  type="radio"
                  name="direction"
                  checked={direction === 'lower'}
                  onChange={() => setDirection('lower')}
                  className="accent-accent"
                />
                Lower is better
              </label>
            </div>
            <p className="text-11 text-text-muted mt-2">
              Required, with no default. A T50 rises with stability; a ΔΔG reported
              destabilizing-positive falls with it. Every rank statistic on the scorecard needs
              this to orient itself, and it is not something this product will guess.
            </p>
          </fieldset>

          <div className="flex items-center gap-3 pt-1">
            <Button onClick={() => void onImport()} disabled={!canImport}>
              <Check className="size-4" strokeWidth={1.5} />
              Import {preview.total_rows.toLocaleString()} measurements
            </Button>
            {direction === 'unset' ? (
              <span className="text-12 text-text-muted">
                State which direction is better to continue.
              </span>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  )
}

function ColumnPicker({
  label,
  headers,
  value,
  onChange,
  required = false,
  allowNone = false,
}: {
  label: string
  headers: Inspect
  value: string
  onChange: (next: string) => void
  required?: boolean
  allowNone?: boolean
}) {
  const sample = headers.columns.find((column) => column.name === value)?.sample ?? []
  const pick = (next: string) => onChange(next === NONE ? '' : next)
  return (
    <label className="block">
      <span className="text-12 text-text-muted">
        {label}
        {required ? '' : ' (optional)'}
      </span>
      <Select
        value={value || NONE}
        onValueChange={pick}
        placeholder={allowNone ? 'None' : 'Choose a column'}
        aria-label={label}
        options={[
          { value: NONE, label: allowNone ? 'None' : 'Choose a column' },
          ...headers.headers.map((header) => ({ value: header, label: header })),
        ]}
      />
      {sample.length > 0 ? (
        <span className="text-11 text-text-faint mt-1 block truncate font-mono">
          {sample.slice(0, 3).join(', ')}
        </span>
      ) : null}
    </label>
  )
}

/**
 * A numbering shift the product found but has not applied.
 *
 * It shows the evidence and both outcomes — what accepting it would fix, and
 * what it would leave unfixed — because a proposal that overstates its effect is
 * one the user cannot weigh. Applying it is a button press, never a default.
 */
function OffsetProposalPanel({
  proposal,
  schemeLabel,
  busy,
  onAccept,
}: {
  proposal: NonNullable<MeasurementPreview['offset']>
  schemeLabel: string
  busy: boolean
  onAccept: () => void
}) {
  return (
    <section
      role="alert"
      aria-label="Numbering shift proposal"
      className="border-warn/30 bg-warn/8 rounded-panel border p-4"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle className="text-warn mt-0.5 size-4 shrink-0" strokeWidth={1.5} />
        <div className="space-y-2">
          <p className="text-13 font-strong text-text">
            This file looks like it is numbered {formatOffset(-proposal.offset)} than{' '}
            {schemeLabel}
          </p>
          <p className="text-12 text-text-muted">
            All {proposal.witnesses.toLocaleString()} unplaced rows are explained by one constant
            shift of {formatSigned(proposal.offset)}, and no other shift explains them. Nothing
            has been changed — accepting this re-runs the join, it does not edit the file.
          </p>

          <ul className="text-12 text-text space-y-0.5 font-mono">
            {proposal.would_join.slice(0, 4).map((row) => (
              <li key={row.index}>
                {row.raw_label} → {row.code}
              </li>
            ))}
          </ul>

          <p className="text-12 text-text-muted">
            {proposal.would_join.length.toLocaleString()} rows would join.
            {proposal.explained_without_variant.length > 0
              ? ` ${proposal.explained_without_variant.length.toLocaleString()} would still not, because this target has no variant for them.`
              : ''}
          </p>

          <Button onClick={onAccept} disabled={busy}>
            Apply shift of {formatSigned(proposal.offset)}
          </Button>
        </div>
      </div>
    </section>
  )
}

function PreviewTable({ preview }: { preview: MeasurementPreview }) {
  return (
    <div className="border-border rounded-panel overflow-hidden border">
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>Row</TableHeaderCell>
            <TableHeaderCell>As written</TableHeaderCell>
            <TableHeaderCell numeric>Value</TableHeaderCell>
            <TableHeaderCell>Joins to</TableHeaderCell>
            <TableHeaderCell>Outcome</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {preview.rows.map((row) => (
            <TableRow key={row.index}>
              <TableCell numeric>{row.index}</TableCell>
              <TableCell mono>{row.raw_label}</TableCell>
              <TableCell numeric>{row.value}</TableCell>
              <TableCell mono>{row.code ?? '—'}</TableCell>
              <TableCell>
                {row.code ? (
                  <Badge tone="positive">joined</Badge>
                ) : (
                  <span className="text-12 text-text-muted">{row.detail}</span>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {preview.total_rows > preview.rows.length ? (
        <p className="text-11 text-text-muted bg-surface-sunk border-border border-t px-2 py-1">
          Showing the first {preview.rows.length} of {preview.total_rows.toLocaleString()} rows.
          The join and the shift proposal were computed over all of them.
        </p>
      ) : null}
    </div>
  )
}

function formatSigned(value: number): string {
  return `${value >= 0 ? '+' : ''}${value}`
}

function formatOffset(value: number): string {
  const magnitude = Math.abs(value)
  return `${magnitude} ${magnitude === 1 ? 'position' : 'positions'} ${value >= 0 ? 'higher' : 'lower'}`
}
