'use client'

import type { Additive, DesignMember, DesignSet, PairFlag } from '@catalyst/schema'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { useState } from 'react'

import { EpistasisWarningPanel } from '@/components/design/epistasis-warning'
import { InlineError } from '@/components/inline-error'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  EmptyCell,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from '@/components/ui/table'
import { Tooltip } from '@/components/ui/tooltip'
import * as api from '@/lib/api'

/**
 * Screen §5.7 — the design set builder.
 *
 * The panel's whole job is to keep three things impossible to miss: what the
 * additivity assumption is, which pairs are close enough to interact, and which
 * pairs nobody measured. The third is the one a naive build gets wrong, because
 * an unmeasured pair looks exactly like a safe one unless the interface goes out
 * of its way to say otherwise.
 */
export function DesignSetPanel({ initial }: { initial: DesignSet }) {
  const client = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [remedy, setRemedy] = useState<string>('')

  const query = useQuery({
    queryKey: ['design-set', initial.design_set_id],
    queryFn: () => api.fetchDesignSet(initial.design_set_id),
    initialData: initial,
  })
  const set = query.data ?? initial

  const remove = useMutation({
    mutationFn: (variantId: string) =>
      api.removeDesignMember(set.design_set_id, variantId),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ['design-set', set.design_set_id] }),
    onError: (thrown: unknown) => {
      const failure = thrown as { message?: string; remedy?: string }
      setError(failure.message ?? 'That design could not be removed.')
      setRemedy(failure.remedy ?? 'Reload the page and try again.')
    },
  })

  const stacked = set.members.filter((member) => member.is_stacked)
  const singles = set.members.filter((member) => !member.is_stacked)

  return (
    <div className="space-y-6 p-4">
      <header className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-18 font-strong">{set.name}</h1>
        {set.is_demo ? <Badge tone="warn">Synthetic output</Badge> : null}
        <span className="text-12 text-text-muted">
          {set.scheme_label ? `Numbering: ${set.scheme_label}` : 'No confirmed scheme'}
        </span>
        <span className="text-12 text-text-muted tabular-nums">
          {singles.length.toLocaleString()} single ·{' '}
          {stacked.length.toLocaleString()} stacked
        </span>
      </header>

      {set.note ? <p className="text-13 text-text-muted">{set.note}</p> : null}

      {error ? <InlineError message={error} remedy={remedy} /> : null}

      <EpistasisWarningPanel warning={set.warning} />

      <BudgetBar set={set} />

      {set.members.length === 0 ? (
        <p className="text-13 text-text-muted">
          No designs yet. Select variants in the workbench and add them to this set.
        </p>
      ) : (
        <section className="space-y-2">
          <h2 className="text-15 font-strong">Designs</h2>
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Mutation</TableHeaderCell>
                <TableHeaderCell>Three-letter</TableHeaderCell>
                <TableHeaderCell>Kind</TableHeaderCell>
                <TableHeaderCell>Pairs</TableHeaderCell>
                <TableHeaderCell>Assumed additive totals</TableHeaderCell>
                <TableHeaderCell>
                  <span className="sr-only">Remove</span>
                </TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {set.members.map((member) => (
                <MemberRow
                  key={member.variant_id}
                  member={member}
                  onRemove={() => remove.mutate(member.variant_id)}
                />
              ))}
            </TableBody>
          </Table>
        </section>
      )}

      {set.geometry_note ? (
        <p className="text-12 text-text-muted">{set.geometry_note}</p>
      ) : null}
    </div>
  )
}

function MemberRow({
  member,
  onRemove,
}: {
  member: DesignMember
  onRemove: () => void
}) {
  return (
    <TableRow>
      <TableCell mono>{member.code}</TableCell>
      <TableCell mono muted>
        {member.hgvs}
      </TableCell>
      <TableCell>
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-12 text-text-muted">
            {member.is_stacked ? `${member.mutations.length} mutations` : 'Single'}
          </span>
          {member.included_via_override ? (
            <Tooltip content={member.override_reason ?? 'Constraint overridden.'}>
              <Badge tone="warn">Override</Badge>
            </Tooltip>
          ) : null}
        </div>
      </TableCell>
      <TableCell>
        {member.is_stacked ? <PairList pairs={member.pairs} /> : <EmptyCell reason="A single-point design has no pair to flag." />}
      </TableCell>
      <TableCell>
        {member.is_stacked ? (
          <AdditiveList estimates={member.additive} />
        ) : (
          <EmptyCell reason="Nothing is assumed for a single mutation — its score is the model's own." />
        )}
      </TableCell>
      <TableCell>
        <Button size="sm" variant="danger" onClick={onRemove}>
          <Trash2 strokeWidth={1.5} />
          Remove
        </Button>
      </TableCell>
    </TableRow>
  )
}

/**
 * Every pair renders in one of three states and `unknown` is visually distinct
 * from `beyond`. Collapsing them would be the defect this whole feature exists
 * to avoid.
 */
function PairList({ pairs }: { pairs: PairFlag[] }) {
  if (pairs.length === 0) return <EmptyCell reason="No pair to measure." />

  return (
    <ul className="space-y-0.5">
      {pairs.map((pair) => {
        const key = `${pair.a_code}-${pair.b_code}`
        if (pair.proximity === 'unknown') {
          return (
            <li key={key} className="text-12 flex items-center gap-1.5">
              <span className="font-mono">
                {pair.a_code} · {pair.b_code}
              </span>
              <Tooltip content={pair.reason ?? 'Not measured.'}>
                <span className="text-text-faint">not measured</span>
              </Tooltip>
            </li>
          )
        }
        const within = pair.proximity === 'within'
        return (
          <li key={key} className="text-12 flex items-center gap-1.5">
            <span className="font-mono">
              {pair.a_code} · {pair.b_code}
            </span>
            <span className={within ? 'text-warn tabular-nums' : 'text-text-muted tabular-nums'}>
              {pair.separation_angstrom?.toFixed(1)} Å
            </span>
            {within ? <Badge tone="warn">Within 8 Å</Badge> : null}
          </li>
        )
      })}
    </ul>
  )
}

function AdditiveList({ estimates }: { estimates: Additive[] }) {
  if (estimates.length === 0) return <EmptyCell reason="No scored metric to sum." />

  return (
    <ul className="space-y-0.5">
      {estimates.map((estimate) => (
        <li key={estimate.metric} className="text-12 flex items-center gap-1.5">
          <span className="text-text-muted">{estimate.label}</span>
          {estimate.total === null ? (
            <EmptyCell
              reason={`No total: ${estimate.missing.join(', ')} ${
                estimate.missing.length === 1 ? 'has' : 'have'
              } no value for this metric, and a partial sum would understate the design.`}
            />
          ) : (
            <Tooltip
              content={`${estimate.assumption} ${estimate.interval_note} Sign convention: ${estimate.sign_convention}.`}
            >
              <span className="text-text tabular-nums">
                {estimate.total.toFixed(2)}
                {estimate.unit ? ` ${estimate.unit}` : ''}
              </span>
            </Tooltip>
          )}
        </li>
      ))}
    </ul>
  )
}

/**
 * Running budget and cost estimate, §5.7.
 *
 * The total is frequently absent, and that is correct behaviour rather than an
 * unfinished feature: no vendor price is invented here, so an unpriced project
 * gets the reason instead of a plausible figure attached to a $4,000 ordering
 * decision.
 */
function BudgetBar({ set }: { set: DesignSet }) {
  const { cost } = set
  const currency = cost.currency ?? cost.budget_currency ?? ''

  return (
    <section className="border-border rounded-panel border p-4">
      <h2 className="text-15 font-strong">Budget</h2>
      <dl className="text-13 mt-2 flex flex-wrap gap-x-6 gap-y-1">
        <div className="flex gap-1.5">
          <dt className="text-text-muted">Stated budget</dt>
          <dd className="text-text tabular-nums">
            {cost.budget_amount === null ? (
              <EmptyCell reason="No budget has been set for this design set." />
            ) : (
              `${cost.budget_amount.toLocaleString()} ${cost.budget_currency ?? ''}`.trim()
            )}
          </dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-text-muted">Estimated cost</dt>
          <dd className="text-text tabular-nums">
            {cost.total === null ? (
              <EmptyCell reason={cost.unavailable_reason ?? 'Not costed.'} />
            ) : (
              `${cost.total.toLocaleString()} ${currency}`.trim()
            )}
          </dd>
        </div>
        {cost.remaining !== null ? (
          <div className="flex gap-1.5">
            <dt className="text-text-muted">Remaining</dt>
            <dd
              className={
                cost.over_budget ? 'text-negative tabular-nums' : 'text-text tabular-nums'
              }
            >
              {cost.remaining.toLocaleString()} {currency}
            </dd>
          </div>
        ) : null}
      </dl>
      {cost.unavailable_reason ? (
        <p className="text-12 text-text-muted mt-2">{cost.unavailable_reason}</p>
      ) : null}
    </section>
  )
}
