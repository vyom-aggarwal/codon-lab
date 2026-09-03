'use client'

import type { Goal, GoalSpec, Objective } from '@codonlab/schema'
import { Check, Lock, Pencil, Play } from 'lucide-react'
import type { Route } from 'next'
import { useRouter } from 'next/navigation'
import { useState, useTransition } from 'react'

import {
  confirmGoalAction,
  createGoalAction,
  startRunAction,
  updateGoalAction,
} from '@/app/actions'
import { InlineError } from '@/components/inline-error'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { useToast } from '@/components/ui/toast'

type Failure = { message: string; remedy: string } | null

const OBJECTIVES: { value: Objective; label: string }[] = [
  { value: 'thermostability', label: 'Thermostability' },
  { value: 'activity', label: 'Activity' },
  { value: 'expression', label: 'Expression' },
  { value: 'solubility', label: 'Solubility' },
  { value: 'binding_affinity', label: 'Binding affinity' },
  { value: 'specificity', label: 'Specificity' },
  { value: 'solvent_tolerance', label: 'Solvent tolerance' },
  { value: 'other', label: 'Other' },
]

export function GoalComposer({
  targetId,
  goal,
  disabled,
  objectiveSupport,
}: {
  targetId: string
  goal: Goal | null
  disabled: boolean
  /** Per objective: whether anything runnable covers it, and if not, why. The
      rest are greyed out *with the reason*, per specification §6. */
  objectiveSupport: Record<string, { supported: boolean; reason: string | null }>
}) {
  const router = useRouter()
  const toast = useToast()
  const [pending, startTransition] = useTransition()
  const [error, setError] = useState<Failure>(null)
  const [text, setText] = useState('')

  function submit() {
    setError(null)
    startTransition(async () => {
      const result = await createGoalAction(targetId, text)
      if (!result.ok) {
        setError({ message: result.message, remedy: result.remedy })
        return
      }
      toast({ title: 'Goal parsed', description: 'Check each chip, then confirm.' })
      setText('')
      router.refresh()
    })
  }

  return (
    <div className="max-w-3xl space-y-6">
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault()
          submit()
        }}
      >
        <label className="block space-y-1">
          <span className="text-11 text-text-muted block font-medium uppercase tracking-wide">
            What do you want to change?
          </span>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            aria-label="Engineering goal"
            rows={3}
            disabled={disabled}
            placeholder="Make this enzyme survive 65 C without killing activity, one 96-well plate in E. coli, measured by DSF"
            className="border-border bg-surface text-13 text-text placeholder:text-text-faint hover:border-border-strong rounded-control w-full border p-2 disabled:pointer-events-none disabled:opacity-40"
          />
        </label>
        {error ? <InlineError message={error.message} remedy={error.remedy} /> : null}
        <Button type="submit" variant="primary" disabled={pending || disabled || !text.trim()}>
          {pending ? 'Parsing…' : 'Parse goal'}
        </Button>
      </form>

      {goal ? (
        <ParsedObjective
          goal={goal}
          targetId={targetId}
          objectiveSupport={objectiveSupport}
        />
      ) : null}
    </div>
  )
}

/* ----------------------------------------------------------------- chips */

function ParsedObjective({
  goal,
  targetId,
  objectiveSupport,
}: {
  goal: Goal
  targetId: string
  objectiveSupport: Record<string, { supported: boolean; reason: string | null }>
}) {
  const router = useRouter()
  const toast = useToast()
  const [pending, startTransition] = useTransition()
  const [error, setError] = useState<Failure>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<GoalSpec>(goal.spec)

  // Greyed out from what the providers declare, never from a model named here —
  // and the reason comes from the API, so the explanation is the same sentence
  // wherever it is shown.
  const objectiveOptions = OBJECTIVES.map((option) => {
    const support = objectiveSupport[option.value]
    if (!support || support.supported) return option
    return {
      ...option,
      disabled: true,
      disabledReason:
        support.reason ??
        'No configured predictor covers this objective. Running it would return numbers about something you did not ask for.',
    }
  })

  function save() {
    setError(null)
    startTransition(async () => {
      const result = await updateGoalAction(goal.id, draft)
      if (!result.ok) {
        setError({ message: result.message, remedy: result.remedy })
        return
      }
      // Editing clears confirmation server-side; say so rather than let the
      // user discover the run button has re-locked.
      toast({
        title: 'Objective updated',
        description: 'Confirmation cleared — confirm again before running.',
      })
      setEditing(false)
      router.refresh()
    })
  }

  function confirm() {
    setError(null)
    startTransition(async () => {
      const result = await confirmGoalAction(goal.id)
      if (!result.ok) {
        setError({ message: result.message, remedy: result.remedy })
        return
      }
      toast({ title: 'Objective confirmed' })
      router.refresh()
    })
  }

  function startRun() {
    setError(null)
    startTransition(async () => {
      const result = await startRunAction(goal.id, targetId)
      if (!result.ok) {
        // Including the API's refusal when the objective is not confirmed. The
        // button is disabled for the same reason, but the server is what decides.
        setError({ message: result.message, remedy: result.remedy })
        return
      }
      // The button named its effect; the toast keeps that name.
      toast({ title: 'Design run started', description: 'Stages appear as they run.' })
      router.push(`/runs/${result.data.id}` as Route)
    })
  }

  const spec = editing ? draft : goal.spec

  return (
    <div className="border-border rounded-panel divide-border divide-y border">
      <header className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-15 font-strong">Parsed objective</h2>
          {goal.is_confirmed ? (
            <Badge tone="positive">Confirmed</Badge>
          ) : (
            <Badge tone="warn">Not confirmed</Badge>
          )}
          {/* A keyword match is not a reading of the sentence. Say which it was. */}
          {goal.method === 'rules' ? (
            <Badge tone="warn">Keyword match, not read</Badge>
          ) : goal.method === 'edited' ? (
            <Badge tone="neutral">Edited by hand</Badge>
          ) : (
            <Badge tone="neutral">{goal.method}</Badge>
          )}
        </div>
        {!editing ? (
          <Button size="sm" onClick={() => setEditing(true)}>
            <Pencil aria-hidden="true" strokeWidth={1.5} />
            Edit chips
          </Button>
        ) : null}
      </header>

      <div className="space-y-3 p-4">
        <p className="text-12 text-text-faint italic">&ldquo;{goal.raw_text}&rdquo;</p>
        {goal.note ? <p className="text-12 text-text-muted">{goal.note}</p> : null}

        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Chip label="Objective">
            {editing ? (
              <Select
                aria-label="Objective"
                // Omitted rather than passed as undefined: Radix declares
                // `value?: string`, so under exactOptionalPropertyTypes an
                // explicit undefined is not the same as an absent prop.
                {...(draft.objective ? { value: draft.objective } : {})}
                onValueChange={(value) => setDraft({ ...draft, objective: value as Objective })}
                options={objectiveOptions}
                placeholder="Not stated"
                className="w-full"
              />
            ) : (
              <Value text={spec.objective ? spec.objective.replace(/_/g, ' ') : null} required />
            )}
          </Chip>

          <Chip label="Target value" hint="As written. Never converted.">
            {editing ? (
              <div className="flex gap-2">
                <Input
                  aria-label="Target value"
                  className="w-24"
                  value={draft.target_value?.value ?? ''}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      target_value: event.target.value
                        ? {
                            value: Number(event.target.value),
                            unit: draft.target_value?.unit ?? '°C',
                          }
                        : null,
                    })
                  }
                />
                <Input
                  aria-label="Target unit"
                  className="w-20"
                  value={draft.target_value?.unit ?? ''}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      target_value: draft.target_value
                        ? { ...draft.target_value, unit: event.target.value }
                        : null,
                    })
                  }
                />
              </div>
            ) : (
              <Value
                text={
                  spec.target_value ? `${spec.target_value.value} ${spec.target_value.unit}` : null
                }
              />
            )}
          </Chip>

          <Chip label="Preserve">
            <Value text={spec.preserve.length ? spec.preserve.join(', ') : null} />
          </Chip>

          <Chip label="Budget">
            <Value
              text={
                spec.budget.variants || spec.budget.amount
                  ? [
                      spec.budget.variants ? `${spec.budget.variants} variants` : null,
                      spec.budget.amount
                        ? `${spec.budget.currency ?? ''} ${spec.budget.amount.toLocaleString()}`.trim()
                        : null,
                    ]
                      .filter(Boolean)
                      .join(', ')
                  : null
              }
            />
          </Chip>

          <Chip label="Expression host">
            {editing ? (
              <Input
                aria-label="Expression host"
                value={draft.expression_host ?? ''}
                onChange={(event) =>
                  setDraft({ ...draft, expression_host: event.target.value || null })
                }
              />
            ) : (
              <Value text={spec.expression_host} />
            )}
          </Chip>

          <Chip label="Assay">
            {editing ? (
              <Input
                aria-label="Assay"
                value={draft.assay ?? ''}
                onChange={(event) => setDraft({ ...draft, assay: event.target.value || null })}
              />
            ) : (
              <Value text={spec.assay} />
            )}
          </Chip>
        </dl>

        {spec.unparsed.length > 0 ? (
          <div className="border-warn/30 bg-warn/8 rounded-control border p-2">
            <p className="text-12 text-text font-medium">Not understood</p>
            <ul className="text-12 text-text-muted mt-1 space-y-0.5">
              {spec.unparsed.map((clause) => (
                <li key={clause}>&ldquo;{clause}&rdquo;</li>
              ))}
            </ul>
            <p className="text-12 text-text-faint mt-1">
              These clauses were not placed into any chip. Nothing was inferred from them.
            </p>
          </div>
        ) : null}

        {editing ? (
          <div className="flex gap-2">
            <Button variant="primary" size="sm" disabled={pending} onClick={save}>
              {pending ? 'Saving…' : 'Save chips'}
            </Button>
            <Button
              size="sm"
              onClick={() => {
                setDraft(goal.spec)
                setEditing(false)
              }}
            >
              Cancel
            </Button>
          </div>
        ) : null}
      </div>

      <div className="bg-surface-sunk space-y-2 p-4">
        <p className="text-11 text-text-muted font-medium uppercase tracking-wide">
          In plain English
        </p>
        {/* Built from the parsed fields, not echoed from the input — an echo
            would read correctly no matter what was actually understood. */}
        <p className="text-13 text-text">{goal.restatement}</p>
      </div>

      <Expectations goal={goal} />

      <footer className="space-y-3 p-4">
        {error ? <InlineError message={error.message} remedy={error.remedy} /> : null}

        {goal.missing_required.length > 0 ? (
          <p className="text-12 text-warn">
            Incomplete: {goal.missing_required.join(', ')} not set. Edit the chips to supply it.
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            disabled={pending || editing || goal.is_confirmed || goal.missing_required.length > 0}
            onClick={confirm}
          >
            <Check aria-hidden="true" strokeWidth={1.5} />
            {goal.is_confirmed ? 'Confirmed' : 'Confirm objective'}
          </Button>

          {/* Disabled for the same reason the API would refuse, not for a
              reason invented on the client — and the API refuses regardless. */}
          <Button
            variant={goal.is_confirmed ? 'primary' : 'default'}
            disabled={pending || editing || !goal.is_confirmed}
            title={runBlockedReason(goal) ?? undefined}
            onClick={startRun}
          >
            {goal.is_confirmed ? <Play aria-hidden="true" strokeWidth={1.5} /> : <Lock aria-hidden="true" strokeWidth={1.5} />}
            Start design run
          </Button>

          <span className="text-12 text-text-muted">
            {goal.is_confirmed
              ? 'Scores every single substitution, then ranks what the constraints allow.'
              : 'No run can start from an unconfirmed objective.'}
          </span>
        </div>
      </footer>
    </div>
  )
}

function runBlockedReason(goal: Goal): string | null {
  if (goal.missing_required.length > 0) {
    return `This objective is incomplete: ${goal.missing_required.join(', ')} not set.`
  }
  if (!goal.is_confirmed) return 'This objective has not been confirmed.'
  return null
}

function Expectations({ goal }: { goal: Goal }) {
  return (
    <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
      <div>
        <p className="text-11 text-positive mb-1 font-medium uppercase tracking-wide">
          What this run will tell you
        </p>
        <ul className="text-12 text-text-muted space-y-1">
          {goal.expectations.will.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>
      <div>
        <p className="text-11 text-warn mb-1 font-medium uppercase tracking-wide">
          What it will not
        </p>
        <ul className="text-12 text-text-muted space-y-1">
          {goal.expectations.will_not.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function Chip({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-1">
      <dt className="text-11 text-text-muted font-medium uppercase tracking-wide">{label}</dt>
      <dd>{children}</dd>
      {hint ? <p className="text-12 text-text-faint">{hint}</p> : null}
    </div>
  )
}

/**
 * An unstated field reads as "not stated", never as a blank that could be
 * mistaken for a value the user chose.
 */
function Value({ text, required = false }: { text: string | null; required?: boolean }) {
  if (text) return <span className="text-13 text-text">{text}</span>
  return (
    <span className={required ? 'text-13 text-warn' : 'text-13 text-text-faint'}>
      {required ? 'Not stated — required' : 'Not stated'}
    </span>
  )
}
