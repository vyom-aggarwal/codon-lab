'use client'

import type { NumberingScheme, Reconciliation, Structure } from '@codonlab/schema'
import { Check, Download } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useState, useTransition } from 'react'

import {
  acceptReconciliationAction,
  attachStructureAction,
  confirmCanonicalAction,
  previewReconciliationAction,
} from '@/app/actions'
import { InlineError } from '@/components/inline-error'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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

export function NumberingPanel({
  targetId,
  schemes,
  structures,
  hasAccession,
  isDesignable,
}: {
  targetId: string
  schemes: NumberingScheme[]
  structures: Structure[]
  hasAccession: boolean
  isDesignable: boolean
}) {
  return (
    <div className="space-y-6">
      <StructureSection targetId={targetId} structures={structures} hasAccession={hasAccession} />
      <CanonicalSection targetId={targetId} schemes={schemes} isDesignable={isDesignable} />
    </div>
  )
}

/* -------------------------------------------------------------- structures */

function StructureSection({
  targetId,
  structures,
  hasAccession,
}: {
  targetId: string
  structures: Structure[]
  hasAccession: boolean
}) {
  const router = useRouter()
  const toast = useToast()
  const [pending, startTransition] = useTransition()
  const [error, setError] = useState<Failure>(null)
  const [pdbId, setPdbId] = useState('')

  function attach(input: { source: 'pdb' | 'alphafold_db'; identifier?: string }) {
    setError(null)
    startTransition(async () => {
      const result = await attachStructureAction(targetId, input)
      if (!result.ok) {
        setError({ message: result.message, remedy: result.remedy })
        return
      }
      toast({ title: 'Structure attached' })
      router.refresh()
    })
  }

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-15 font-strong">Structures</h2>
        <p className="text-12 text-text-muted max-w-2xl">
          A structure supplies the author numbering that has to be reconciled against the sequence.
          Predicted and experimental structures are not interchangeable evidence, so which is which
          is recorded and shown.
        </p>
      </div>

      {structures.length > 0 ? (
        <div className="border-border rounded-panel overflow-hidden border">
          <Table>
            <TableHead>
              <TableRow className="hover:bg-surface-sunk">
                <TableHeaderCell>Identifier</TableHeaderCell>
                <TableHeaderCell>Source</TableHeaderCell>
                <TableHeaderCell>Chain</TableHeaderCell>
                <TableHeaderCell>Content hash</TableHeaderCell>
                <TableHeaderCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {structures.map((structure) => (
                <StructureRow key={structure.id} targetId={targetId} structure={structure} />
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <p className="text-13 text-text-muted">
          No structure attached yet. Add one to reconcile numbering.
        </p>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <label className="space-y-1">
          <span className="text-11 text-text-muted block font-medium uppercase tracking-wide">
            RCSB PDB id
          </span>
          <div className="flex gap-2">
            <Input
              mono
              value={pdbId}
              onChange={(event) => setPdbId(event.target.value)}
              placeholder="1BTL"
              aria-label="PDB id"
              className="w-32"
            />
            <Button
              disabled={pending || !pdbId.trim()}
              onClick={() => attach({ source: 'pdb', identifier: pdbId })}
            >
              <Download strokeWidth={1.5} />
              Fetch
            </Button>
          </div>
        </label>

        <Button
          disabled={pending || !hasAccession}
          onClick={() => attach({ source: 'alphafold_db' })}
          title={
            hasAccession
              ? undefined
              : 'AlphaFold DB is keyed by UniProt accession, and this target has none.'
          }
        >
          Fetch from AlphaFold DB
        </Button>
      </div>

      {error ? <InlineError message={error.message} remedy={error.remedy} /> : null}
    </section>
  )
}

function StructureRow({ targetId, structure }: { targetId: string; structure: Structure }) {
  const router = useRouter()
  const toast = useToast()
  const [pending, startTransition] = useTransition()
  const [preview, setPreview] = useState<Reconciliation | null>(null)
  const [error, setError] = useState<Failure>(null)

  function run(useAlignment: boolean) {
    setError(null)
    startTransition(async () => {
      const result = await previewReconciliationAction(targetId, {
        structure_id: structure.id,
        use_alignment: useAlignment,
      })
      if (!result.ok) {
        setError({ message: result.message, remedy: result.remedy })
        return
      }
      setPreview(result.data)
    })
  }

  function accept(useAlignment: boolean) {
    startTransition(async () => {
      const result = await acceptReconciliationAction(targetId, {
        structure_id: structure.id,
        use_alignment: useAlignment,
      })
      if (!result.ok) {
        setError({ message: result.message, remedy: result.remedy })
        return
      }
      toast({ title: 'Numbering scheme saved', description: 'Confirm a canonical scheme next.' })
      setPreview(null)
      router.refresh()
    })
  }

  return (
    <>
      <TableRow>
        <TableCell mono className="font-medium">
          {structure.identifier}
        </TableCell>
        <TableCell>
          {structure.is_predicted ? (
            <Badge tone="warn">Predicted</Badge>
          ) : (
            <Badge tone="neutral">Experimental</Badge>
          )}
        </TableCell>
        <TableCell mono muted>
          {structure.chain ?? '—'}
        </TableCell>
        <TableCell mono muted title={structure.content_hash}>
          {structure.content_hash.slice(0, 10)}
        </TableCell>
        <TableCell className="text-right">
          <Button size="sm" disabled={pending} onClick={() => run(false)}>
            {pending ? 'Working…' : 'Reconcile numbering'}
          </Button>
        </TableCell>
      </TableRow>

      {error || preview ? (
        <TableRow className="hover:bg-surface">
          <TableCell colSpan={5} className="p-0">
            <div className="bg-surface-sunk border-border space-y-3 border-t p-4">
              {error ? <InlineError message={error.message} remedy={error.remedy} /> : null}
              {preview ? (
                <ReconciliationReview
                  preview={preview}
                  pending={pending}
                  onAlign={() => run(true)}
                  onAccept={() => accept(preview.method === 'alignment')}
                  onDismiss={() => setPreview(null)}
                />
              ) : null}
            </div>
          </TableCell>
        </TableRow>
      ) : null}
    </>
  )
}

function ReconciliationReview({
  preview,
  pending,
  onAlign,
  onAccept,
  onDismiss,
}: {
  preview: Reconciliation
  pending: boolean
  onAlign: () => void
  onAccept: () => void
  onDismiss: () => void
}) {
  const resolved = preview.outcome === 'reconciled'

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={resolved ? 'positive' : 'warn'}>
          {resolved ? `Reconciled by ${preview.method}` : preview.outcome.replace('_', ' ')}
        </Badge>
        <span className="text-12 text-text-muted">Chain {preview.chain_id}</span>
        {resolved ? (
          <span className="text-12 text-text-muted tabular-nums">
            {preview.covered} of {preview.total} residues resolved ·{' '}
            {(preview.coverage * 100).toFixed(1)}% coverage · {(preview.identity * 100).toFixed(2)}%
            identity
          </span>
        ) : null}
      </div>

      <p className="text-12 text-text-muted max-w-3xl">{preview.note}</p>

      {preview.parameters ? (
        <p className="text-11 text-text-faint font-mono">
          {Object.entries(preview.parameters)
            .map(([key, value]) => `${key} ${value}`)
            .join('  ·  ')}
        </p>
      ) : null}

      {preview.mismatches.length > 0 ? (
        <div className="space-y-1">
          <p className="text-12 text-text font-medium">
            {preview.mismatches.length} position
            {preview.mismatches.length === 1 ? '' : 's'} where the structure and the sequence
            disagree
          </p>
          <ul className="text-12 text-text-muted space-y-0.5 font-mono">
            {preview.mismatches.slice(0, 12).map((mismatch) => (
              <li key={`${mismatch.sequence_position}-${mismatch.structure_label}`}>
                sequence {mismatch.sequence_residue}
                {mismatch.sequence_position} · structure {mismatch.structure_residue}
                {mismatch.structure_label}
              </li>
            ))}
          </ul>
          {preview.mismatches.length > 12 ? (
            <p className="text-11 text-text-faint">and {preview.mismatches.length - 12} more</p>
          ) : null}
        </div>
      ) : null}

      <div className="flex gap-2">
        {resolved ? (
          <Button variant="primary" size="sm" disabled={pending} onClick={onAccept}>
            Save this numbering scheme
          </Button>
        ) : preview.outcome === 'needs_alignment' ? (
          <Button variant="primary" size="sm" disabled={pending} onClick={onAlign}>
            {pending ? 'Aligning…' : 'Align and show differences'}
          </Button>
        ) : null}
        <Button size="sm" onClick={onDismiss}>
          Dismiss
        </Button>
      </div>
    </div>
  )
}

/* ----------------------------------------------------------- canonical pick */

function CanonicalSection({
  targetId,
  schemes,
  isDesignable,
}: {
  targetId: string
  schemes: NumberingScheme[]
  isDesignable: boolean
}) {
  const router = useRouter()
  const toast = useToast()
  const [pending, startTransition] = useTransition()
  const [error, setError] = useState<Failure>(null)
  // Deliberately starts empty. Nothing is pre-selected: a default here could be
  // accepted by inattention, and the whole point is that the choice is made.
  const [selected, setSelected] = useState<string | null>(null)

  function confirm() {
    if (!selected) return
    setError(null)
    startTransition(async () => {
      const result = await confirmCanonicalAction(targetId, selected)
      if (!result.ok) {
        setError({ message: result.message, remedy: result.remedy })
        return
      }
      toast({
        title: 'Canonical scheme confirmed',
        ...(result.data.label ? { description: result.data.label } : {}),
      })
      router.refresh()
    })
  }

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-15 font-strong">Canonical numbering scheme</h2>
        <p className="text-12 text-text-muted max-w-2xl">
          Every mutation code in this project is written in the scheme chosen here, and its name is
          shown alongside each code. Nothing is pre-selected — these schemes disagree with one
          another, and picking the wrong one silently shifts every residue number downstream.
        </p>
      </div>

      <fieldset className="space-y-2">
        <legend className="sr-only">Choose a canonical numbering scheme</legend>
        {schemes.map((scheme) => (
          <label
            key={scheme.id}
            className="border-border hover:border-border-strong rounded-panel has-checked:border-accent has-checked:bg-accent-sunk flex cursor-pointer items-start gap-3 border p-3"
          >
            <input
              type="radio"
              name="canonical-scheme"
              value={scheme.id}
              checked={selected === scheme.id}
              onChange={() => setSelected(scheme.id)}
              className="accent-accent mt-0.5"
            />
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-13 text-text font-medium">{scheme.label}</span>
                {scheme.is_canonical ? <Badge tone="positive">Current</Badge> : null}
                <Badge tone="neutral">{scheme.kind.replace('_', ' ')}</Badge>
              </div>
              <p className="text-12 text-text-muted font-mono tabular-nums">
                {scheme.first_label} … {scheme.last_label} · {scheme.covered} residues covered
              </p>
              {scheme.note ? <p className="text-12 text-text-muted">{scheme.note}</p> : null}
            </div>
          </label>
        ))}
      </fieldset>

      {error ? <InlineError message={error.message} remedy={error.remedy} /> : null}

      <div className="flex items-center gap-3">
        <Button variant="primary" disabled={pending || !selected} onClick={confirm}>
          <Check strokeWidth={1.5} />
          {pending ? 'Confirming…' : 'Confirm scheme'}
        </Button>
        {!selected ? (
          <span className="text-12 text-text-faint">Select a scheme to continue.</span>
        ) : null}
        {isDesignable ? (
          <span className="text-12 text-positive inline-flex items-center gap-1">
            <Check className="size-4" strokeWidth={1.5} />
            This target can be designed against.
          </span>
        ) : null}
      </div>
    </section>
  )
}
