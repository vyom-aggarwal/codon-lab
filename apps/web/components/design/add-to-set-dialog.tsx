'use client'

import type { DesignSetSummary } from '@catalyst/schema'
import type { Route } from 'next'
import { Layers } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useState } from 'react'

import { InlineError } from '@/components/inline-error'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogTrigger } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { useToast } from '@/components/ui/toast'
import * as api from '@/lib/api'

/**
 * Adds the workbench selection to a design set — specification §5.7.
 *
 * The constraint-override flow lives here rather than being pre-empted: the
 * dialog sends the request without an override first, and the reason field only
 * appears once the **API** has refused. A screen that decided for itself which
 * positions are constrained would be a second implementation of the rule, free
 * to disagree with the one in `services/design_sets` that actually guards it.
 */
export function AddToSetDialog({
  runId,
  codes,
  existing,
  onAdded,
}: {
  runId: string
  codes: string[]
  existing: DesignSetSummary[]
  onAdded?: () => void
}) {
  const router = useRouter()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<{ message: string; remedy: string } | null>(null)
  const [needsOverride, setNeedsOverride] = useState(false)
  const [overrideReason, setOverrideReason] = useState('')
  const [name, setName] = useState('')
  const [budget, setBudget] = useState('')
  const [currency, setCurrency] = useState('')
  const [targetSet, setTargetSet] = useState<string>(existing[0]?.design_set_id ?? '')

  function reset() {
    setError(null)
    setNeedsOverride(false)
    setOverrideReason('')
  }

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      let setId = targetSet
      if (!setId) {
        const created = await api.createDesignSet(runId, {
          name: name.trim() || 'Untitled design set',
          budget_amount: budget.trim() === '' ? null : Number(budget),
          budget_currency: currency.trim() === '' ? null : currency.trim(),
        })
        setId = created.design_set_id
      }

      await api.addDesignMembers(setId, {
        codes,
        override: needsOverride,
        // Omitted rather than sent as undefined: `exactOptionalPropertyTypes`
        // treats an explicit undefined as a distinct value from an absent key.
        ...(needsOverride ? { override_reason: overrideReason } : {}),
      })

      toast({ title: 'Designs added' })
      setOpen(false)
      reset()
      onAdded?.()
      router.push(`/runs/${runId}/design-sets/${setId}` as Route)
    } catch (thrown) {
      const failure = thrown as { message?: string; remedy?: string }
      const message = failure.message ?? 'Those designs could not be added.'
      setError({ message, remedy: failure.remedy ?? 'Check the input and try again.' })
      // The API names the constrained positions in the refusal. That refusal is
      // what opens the override field — §7 requires the override to be explicit.
      if (message.includes('constrained positions')) setNeedsOverride(true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) reset()
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm" disabled={codes.length === 0}>
          <Layers strokeWidth={1.5} />
          Add to design set
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Add to design set"
        description={`${codes.length.toLocaleString()} design${codes.length === 1 ? '' : 's'} selected.`}
      >
        <div className="space-y-3">
          {existing.length > 0 ? (
            <label className="block space-y-1">
              <span className="text-12 text-text-muted">Design set</span>
              <select
                className="border-border bg-surface text-13 rounded-control h-control w-full border px-2"
                value={targetSet}
                onChange={(event) => setTargetSet(event.target.value)}
              >
                {existing.map((set) => (
                  <option key={set.design_set_id} value={set.design_set_id}>
                    {set.name}
                  </option>
                ))}
                <option value="">New design set</option>
              </select>
            </label>
          ) : null}

          {targetSet === '' ? (
            <>
              <label className="block space-y-1">
                <span className="text-12 text-text-muted">Name</span>
                <Input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Thermostability round 1"
                />
              </label>
              <div className="flex gap-2">
                <label className="block flex-1 space-y-1">
                  <span className="text-12 text-text-muted">Budget</span>
                  <Input
                    value={budget}
                    inputMode="decimal"
                    onChange={(event) => setBudget(event.target.value)}
                    placeholder="4000"
                  />
                </label>
                <label className="block w-24 space-y-1">
                  <span className="text-12 text-text-muted">Currency</span>
                  <Input
                    value={currency}
                    onChange={(event) => setCurrency(event.target.value)}
                    placeholder="USD"
                  />
                </label>
              </div>
            </>
          ) : null}

          {error ? <InlineError message={error.message} remedy={error.remedy} /> : null}

          {needsOverride ? (
            <label className="block space-y-1">
              <span className="text-12 text-text-muted">
                Why may this constrained position be mutated?
              </span>
              <Input
                value={overrideReason}
                onChange={(event) => setOverrideReason(event.target.value)}
                placeholder="Probing the catalytic residue deliberately; activity loss expected."
              />
              <span className="text-11 text-text-muted block">
                Recorded against this design set as a provenance event.
              </span>
            </label>
          ) : null}
        </div>

        <DialogFooter>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button
            variant="primary"
            onClick={submit}
            disabled={busy || (needsOverride && overrideReason.trim() === '')}
          >
            {needsOverride ? 'Override and add' : 'Add to design set'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
