import type { EpistasisWarning } from '@codonlab/schema'
import { AlertTriangle } from 'lucide-react'

/**
 * Specification §5.7: "an unmissable warning that stacked effects are assumed
 * additive and frequently are not (epistasis)".
 *
 * Three properties make it unmissable rather than merely present:
 *
 * - It is **not dismissible**, like the demo bar. A warning a user can close is
 *   a warning that is absent from the screenshot that ends up in a slide deck.
 * - It renders **whenever the set holds a stacked design**, driven by
 *   `stacked_designs` from the API rather than by any judgement made here.
 * - It reports **unknown pairs beside flagged pairs**. A panel that showed only
 *   "1 pair within 8 A" for a target with no structure would be stating that
 *   the other pairs were checked and found distant. They were not checked.
 *
 * The wording of the assumption itself comes from the API (`domain/epistasis`),
 * so the sentence lives with the arithmetic that needs it and a second screen
 * cannot quietly soften it.
 */
export function EpistasisWarningPanel({ warning }: { warning: EpistasisWarning }) {
  if (warning.stacked_designs === 0) return null

  const flagged = warning.pairs_within_cutoff
  const unknown = warning.pairs_unknown

  return (
    <section
      role="alert"
      aria-label="Epistasis warning"
      className="border-warn/30 bg-warn/8 rounded-panel border p-4"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle className="text-warn mt-0.5 size-4 shrink-0" strokeWidth={1.5} />
        <div className="space-y-2">
          <p className="text-13 font-strong text-text">
            Stacked effects are assumed additive
          </p>
          <p className="text-12 text-text-muted">{warning.assumption}</p>

          <dl className="text-12 flex flex-wrap gap-x-6 gap-y-1">
            <div className="flex gap-1.5">
              <dt className="text-text-muted">Stacked designs</dt>
              <dd className="text-text tabular-nums">
                {warning.stacked_designs.toLocaleString()}
              </dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-text-muted">
                Pairs within {warning.cutoff_angstrom} Å
              </dt>
              <dd className={flagged > 0 ? 'text-warn tabular-nums' : 'text-text tabular-nums'}>
                {flagged.toLocaleString()} of {warning.pairs_total.toLocaleString()}
              </dd>
            </div>
            {unknown > 0 ? (
              <div className="flex gap-1.5">
                <dt className="text-text-muted">Pairs not measured</dt>
                <dd className="text-text tabular-nums">{unknown.toLocaleString()}</dd>
              </div>
            ) : null}
          </dl>

          {unknown > 0 ? (
            <p className="text-12 text-text-muted">
              A pair that was not measured is not a pair that was found distant. Those{' '}
              {unknown.toLocaleString()} read as unknown below, each with the reason.
            </p>
          ) : null}

          <p className="text-11 text-text-muted">
            Separation is the {warning.distance_convention}.
          </p>
        </div>
      </div>
    </section>
  )
}
