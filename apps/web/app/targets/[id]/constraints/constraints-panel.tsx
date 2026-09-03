'use client'

import type { Constraint, ConstraintKind, Suggestion } from '@codonlab/schema'
import { Plus, Trash2 } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useState, useTransition } from 'react'

import { addConstraintAction, removeConstraintAction } from '@/app/actions'
import { InlineError } from '@/components/inline-error'
import { Badge } from '@/components/ui/badge'
import { Button, IconButton } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from '@/components/ui/table'
import { useToast } from '@/components/ui/toast'

type Failure = { message: string; remedy: string } | null

const KINDS: { value: ConstraintKind; label: string }[] = [
  { value: 'catalytic', label: 'Catalytic residue' },
  { value: 'ligand_contact', label: 'Ligand contact' },
  { value: 'cofactor_contact', label: 'Cofactor contact' },
  { value: 'binding_interface', label: 'Binding interface' },
  { value: 'disulfide', label: 'Disulfide' },
  { value: 'signal_peptide', label: 'Signal peptide' },
  { value: 'purification_tag', label: 'Purification tag' },
  { value: 'do_not_touch', label: 'Do not touch' },
]

const KIND_LABEL = new Map(KINDS.map((kind) => [kind.value, kind.label]))

export function ConstraintsPanel({
  targetId,
  sequenceLength,
  constraints,
  suggestions,
  suggestionError,
  disabled,
}: {
  targetId: string
  sequenceLength: number
  constraints: Constraint[]
  suggestions: Suggestion[]
  suggestionError: string | null
  disabled: boolean
}) {
  const applied = new Set(
    constraints.map((constraint) => `${constraint.kind}:${constraint.positions.join(',')}`),
  )

  return (
    <div className="space-y-6">
      <Suggestions
        targetId={targetId}
        suggestions={suggestions.filter(
          (suggestion) => !applied.has(`${suggestion.kind}:${suggestion.positions.join(',')}`),
        )}
        error={suggestionError}
        disabled={disabled}
      />
      <Applied targetId={targetId} constraints={constraints} />
      <AddByHand targetId={targetId} sequenceLength={sequenceLength} disabled={disabled} />
    </div>
  )
}

/* ------------------------------------------------------------ suggestions */

function Suggestions({
  targetId,
  suggestions,
  error,
  disabled,
}: {
  targetId: string
  suggestions: Suggestion[]
  error: string | null
  disabled: boolean
}) {
  const router = useRouter()
  const toast = useToast()
  const [pending, startTransition] = useTransition()
  const [failure, setFailure] = useState<Failure>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())

  function toggle(index: number) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

  function acceptSelected() {
    setFailure(null)
    startTransition(async () => {
      for (const index of selected) {
        const suggestion = suggestions[index]
        if (!suggestion) continue
        const result = await addConstraintAction(targetId, {
          kind: suggestion.kind,
          positions: suggestion.positions,
          note: suggestion.note,
        })
        if (!result.ok) {
          setFailure({ message: result.message, remedy: result.remedy })
          return
        }
      }
      toast({
        title: `${selected.size} constraint${selected.size === 1 ? '' : 's'} added`,
      })
      setSelected(new Set())
      router.refresh()
    })
  }

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-15 font-strong">Suggested from UniProt</h2>
        <p className="text-12 text-text-muted max-w-3xl">
          Read from the record and translated into this target&rsquo;s canonical numbering. Each one
          shows the position UniProt gave and the position it becomes here — doing that translation
          by hand is where a catalytic residue gets misplaced. None of these constrains anything
          until you accept it.
        </p>
      </div>

      {error ? (
        <p className="text-12 text-text-muted">{error}</p>
      ) : suggestions.length === 0 ? (
        <p className="text-13 text-text-muted">No unapplied suggestions for this target.</p>
      ) : (
        <>
          <ul className="space-y-2">
            {suggestions.map((suggestion, index) => (
              <li key={`${suggestion.kind}-${suggestion.positions.join(',')}`}>
                <label className="border-border hover:border-border-strong rounded-panel has-checked:border-accent has-checked:bg-accent-sunk flex cursor-pointer items-start gap-3 border p-3">
                  <input
                    type="checkbox"
                    checked={selected.has(index)}
                    onChange={() => toggle(index)}
                    disabled={disabled}
                    className="accent-accent mt-0.5"
                    aria-label={`Accept ${suggestion.kind} constraint`}
                  />
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="neutral">
                        {KIND_LABEL.get(suggestion.kind) ?? suggestion.kind}
                      </Badge>
                      <span className="text-12 text-text-faint">{suggestion.source}</span>
                      <span className="text-12 text-text-muted tabular-nums">
                        {suggestion.positions.length} residue
                        {suggestion.positions.length === 1 ? '' : 's'}
                      </span>
                    </div>
                    <p className="text-12 text-text-muted font-mono">{suggestion.note}</p>
                  </div>
                </label>
              </li>
            ))}
          </ul>

          {failure ? <InlineError message={failure.message} remedy={failure.remedy} /> : null}

          <Button
            variant="primary"
            disabled={pending || disabled || selected.size === 0}
            onClick={acceptSelected}
          >
            {pending ? 'Adding…' : `Accept ${selected.size || ''} selected`.trim()}
          </Button>
        </>
      )}
    </section>
  )
}

/* ---------------------------------------------------------------- applied */

function Applied({ targetId, constraints }: { targetId: string; constraints: Constraint[] }) {
  const router = useRouter()
  const toast = useToast()
  const [pending, startTransition] = useTransition()
  const [failure, setFailure] = useState<Failure>(null)

  function remove(constraintId: string) {
    setFailure(null)
    startTransition(async () => {
      const result = await removeConstraintAction(constraintId, targetId)
      if (!result.ok) {
        setFailure({ message: result.message, remedy: result.remedy })
        return
      }
      toast({ title: 'Constraint removed' })
      router.refresh()
    })
  }

  return (
    <section className="space-y-3">
      <h2 className="text-15 font-strong">Applied constraints</h2>

      {constraints.length === 0 ? (
        <p className="text-13 text-text-muted">
          No constraints yet. Accept a suggestion, or add one by hand below.
        </p>
      ) : (
        <>
          <div className="border-border rounded-panel overflow-hidden border">
            <Table>
              <TableHead>
                <TableRow className="hover:bg-surface-sunk">
                  <TableHeaderCell>Kind</TableHeaderCell>
                  <TableHeaderCell numeric>Residues</TableHeaderCell>
                  <TableHeaderCell>Positions</TableHeaderCell>
                  <TableHeaderCell>Note</TableHeaderCell>
                  <TableHeaderCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {constraints.map((constraint) => (
                  <TableRow key={constraint.id}>
                    <TableCell className="font-medium">
                      {KIND_LABEL.get(constraint.kind) ?? constraint.kind}
                    </TableCell>
                    <TableCell numeric muted>
                      {constraint.positions.length}
                    </TableCell>
                    <TableCell mono muted className="max-w-xs truncate">
                      {constraint.labels.join(', ')}
                    </TableCell>
                    <TableCell muted className="max-w-md truncate" title={constraint.note ?? ''}>
                      {constraint.note ?? '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      <IconButton
                        size="sm"
                        variant="danger"
                        label="Remove constraint"
                        icon={<Trash2 aria-hidden="true" strokeWidth={1.5} />}
                        disabled={pending}
                        onClick={() => remove(constraint.id)}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {failure ? <InlineError message={failure.message} remedy={failure.remedy} /> : null}
        </>
      )}
    </section>
  )
}

/* ------------------------------------------------------------ manual add */

function AddByHand({
  targetId,
  sequenceLength,
  disabled,
}: {
  targetId: string
  sequenceLength: number
  disabled: boolean
}) {
  const router = useRouter()
  const toast = useToast()
  const [pending, startTransition] = useTransition()
  const [failure, setFailure] = useState<Failure>(null)
  const [kind, setKind] = useState<ConstraintKind>('do_not_touch')
  const [positions, setPositions] = useState('')
  const [note, setNote] = useState('')

  function submit() {
    setFailure(null)
    const parsed = parsePositions(positions)
    if (parsed.length === 0) {
      setFailure({
        message: 'No positions recognised.',
        remedy: 'Enter positions like 70, 73, 130-134.',
      })
      return
    }

    startTransition(async () => {
      const result = await addConstraintAction(targetId, {
        kind,
        positions: parsed,
        ...(note.trim() ? { note: note.trim() } : {}),
      })
      if (!result.ok) {
        setFailure({ message: result.message, remedy: result.remedy })
        return
      }
      toast({ title: 'Constraint added' })
      setPositions('')
      setNote('')
      router.refresh()
    })
  }

  return (
    <section className="border-border rounded-panel max-w-3xl space-y-3 border p-4">
      <div>
        <h2 className="text-13 font-strong">Add by hand</h2>
        <p className="text-12 text-text-muted">
          Positions are in the canonical numbering scheme, the same numbers shown on the track
          above. This target is {sequenceLength} residues long.
        </p>
      </div>

      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault()
          submit()
        }}
      >
        <div className="flex flex-wrap gap-3">
          <label className="space-y-1">
            <span className="text-11 text-text-muted block font-medium uppercase tracking-wide">
              Kind
            </span>
            <Select
              aria-label="Constraint kind"
              value={kind}
              onValueChange={(value) => setKind(value as ConstraintKind)}
              options={KINDS}
              className="w-56"
            />
          </label>
          <label className="flex-1 space-y-1">
            <span className="text-11 text-text-muted block font-medium uppercase tracking-wide">
              Positions
            </span>
            <Input
              mono
              aria-label="Positions"
              value={positions}
              onChange={(event) => setPositions(event.target.value)}
              placeholder="70, 73, 130-134"
            />
          </label>
        </div>

        <label className="block space-y-1">
          <span className="text-11 text-text-muted block font-medium uppercase tracking-wide">
            Note
          </span>
          <Input
            aria-label="Note"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Why these residues must not change"
          />
        </label>

        {failure ? <InlineError message={failure.message} remedy={failure.remedy} /> : null}

        <Button type="submit" variant="primary" disabled={pending || disabled}>
          <Plus aria-hidden="true" strokeWidth={1.5} />
          {pending ? 'Adding…' : 'Add constraint'}
        </Button>
      </form>
    </section>
  )
}

/**
 * "70, 73, 130-134" into [70, 73, 130, 131, 132, 133, 134].
 *
 * Ranges are inclusive because that is how a biologist reads "130-134".
 * Unparseable fragments are dropped rather than guessed at; the API rejects
 * anything outside the sequence, so a typo surfaces there rather than being
 * silently applied to the wrong residue.
 */
export function parsePositions(text: string): number[] {
  const found = new Set<number>()
  for (const part of text.split(/[,\s]+/)) {
    if (!part) continue
    const range = /^(\d+)\s*-\s*(\d+)$/.exec(part)
    if (range) {
      const start = Number(range[1])
      const end = Number(range[2])
      if (start <= end && end - start < 10_000) {
        for (let position = start; position <= end; position += 1) found.add(position)
      }
      continue
    }
    if (/^\d+$/.test(part)) found.add(Number(part))
  }
  return [...found].sort((a, b) => a - b)
}
