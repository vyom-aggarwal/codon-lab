import type { Filtered } from '@codonlab/schema'

import { Badge } from '@/components/ui/badge'

/**
 * Specification §5.3: constraints are hard filters, and every filtered-out
 * variant is retrievable with the reason shown.
 *
 * The list comes from the provenance event the filter stage wrote, not from
 * today's constraint set, so editing a constraint tomorrow cannot rewrite what
 * this run did.
 */
export function FilteredPanel({ filtered }: { filtered: Filtered }) {
  const removed = Object.entries(filtered.removed)

  if (filtered.override) {
    return (
      <div className="border-warn/30 bg-warn/8 rounded-panel border p-4">
        <p className="text-13 text-text">
          <span className="text-warn font-medium">Constraints overridden.</span> {removed.length}{' '}
          variants at constrained positions were kept in this run. The override is recorded in the
          provenance trail.
        </p>
      </div>
    )
  }

  if (removed.length === 0) {
    return (
      <p className="text-12 text-text-muted">
        No variant was removed by a constraint in this run.
      </p>
    )
  }

  return (
    <details className="border-border rounded-panel border">
      <summary className="text-13 text-text cursor-pointer select-none p-3">
        {removed.length} variants removed by constraints
        <span className="text-text-muted"> — {filtered.kept} kept</span>
      </summary>
      <ul className="divide-border max-h-64 divide-y overflow-y-auto border-t">
        {removed.map(([code, reasons]) => (
          <li key={code} className="flex items-center gap-2 px-3 py-1.5">
            <span className="text-13 font-mono">{code}</span>
            {reasons.map((reason) => (
              <Badge key={reason} tone="warn">
                {reason.replace(/_/g, ' ')}
              </Badge>
            ))}
          </li>
        ))}
      </ul>
    </details>
  )
}
