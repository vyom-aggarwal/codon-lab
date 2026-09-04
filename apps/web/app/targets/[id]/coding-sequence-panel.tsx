'use client'

import { useState } from 'react'

import { InlineError } from '@/components/inline-error'
import { attachCodingSequence } from '@/lib/api'

/**
 * Attach the DNA of the construct on the bench.
 *
 * The whole screen is a text area and a refusal, and the refusal is the part
 * that matters. Everything downstream — primer position, flanking arms, melting
 * temperature — is computed against what this stores, and a wrong sequence does
 * not produce a visibly wrong number. It produces primers that look correct,
 * get synthesised, and do not anneal.
 *
 * So a rejection is rendered as an explanation rather than an error state: what
 * is wrong, at which residue, and what would fix it. The user is holding a tube
 * and a plasmid map; "invalid sequence" tells them nothing they can act on.
 */
export function CodingSequencePanel({
  targetId,
  attached,
}: {
  targetId: string
  /** Bases already stored, if a construct has been attached. */
  attached: number | null
}) {
  const [pasted, setPasted] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Awaited<
    ReturnType<typeof attachCodingSequence>
  > | null>(null)
  const [failure, setFailure] = useState<Error | null>(null)

  const stored = result?.attached ? result.bases : attached

  async function submit() {
    setBusy(true)
    setFailure(null)
    try {
      setResult(await attachCodingSequence(targetId, pasted))
    } catch (error) {
      setFailure(error as Error)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h2 className="text-15 font-strong mb-2">Coding sequence</h2>
      <p className="text-12 text-text-muted mb-3 max-w-2xl">
        The DNA of the construct actually on your bench. Primers anneal to this, so it is
        pasted rather than looked up: a reference CDS is usually codon-optimised
        differently, and back-translating the protein would invent a sequence that is not
        your plasmid. Either would give primers that fail to anneal.
      </p>

      {stored ? (
        <p className="text-12 text-positive mb-3" data-testid="coding-sequence-stored">
          {stored.toLocaleString()} bases attached, translated and checked against this
          target&rsquo;s protein.
        </p>
      ) : null}

      <label className="text-12 text-text-muted mb-1 block" htmlFor="coding-sequence">
        Coding sequence
      </label>
      <textarea
        id="coding-sequence"
        value={pasted}
        onChange={(event) => setPasted(event.target.value)}
        rows={5}
        spellCheck={false}
        placeholder="ATG..."
        className="border-border rounded-control bg-surface text-12 font-mono text-text w-full max-w-2xl border p-2"
      />
      <p className="text-11 text-text-faint mb-3 mt-1">
        FASTA headers, line numbers and whitespace are stripped. Ambiguity codes are not:
        a primer over an unknown base is a primer that may not anneal.
      </p>

      <button
        type="button"
        onClick={submit}
        disabled={busy || !pasted.trim()}
        className="h-control rounded-control bg-accent text-surface text-13 disabled:bg-surface-sunk disabled:text-text-faint px-3"
      >
        {busy ? 'Checking…' : 'Attach'}
      </button>

      {failure ? (
        <div className="mt-3 max-w-2xl">
          <InlineError
            message={failure.message}
            remedy={
              'remedy' in failure && typeof failure.remedy === 'string'
                ? failure.remedy
                : 'Check that the API is reachable, then try again.'
            }
          />
        </div>
      ) : null}

      {result && !result.attached ? (
        <div
          className="border-warn rounded-control mt-3 max-w-2xl border p-3"
          role="status"
          data-testid="coding-sequence-refusal"
        >
          <p className="text-13 text-text">{result.reason}</p>
          <p className="text-12 text-text-muted mt-1">{result.remedy}</p>
          {result.offset ? (
            <p className="text-12 text-text-muted mt-1">
              The stored protein begins {result.offset} residues in. Trimming is not
              offered: every primer position would shift by that much.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
